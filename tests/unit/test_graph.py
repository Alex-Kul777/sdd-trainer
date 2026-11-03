"""Unit tests for the trainer graph at the single test seam (design.md).

The seam is the graph boundary: a real compiled graph whose ``LLMManager``
is wired to a fake OpenAI client and whose docs search is a fake callable
— no network. Asserts target external behavior only (issues #4/#5): the
selected route, the session log, the checkpoint (InMemorySaver for speed,
SqliteSaver on a tmp file to prove a restart resumes from the checkpoint —
criterion 4), and the teach node unfolding the real lesson skeleton per
level with ``search_sdd_docs`` on demand (task 3.3).
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from sdd_trainer.config import GigaChatConfig
from sdd_trainer.core.graph import (
    CLARIFICATION_THRESHOLD,
    MAX_CLARIFICATION_ROUNDS,
    build_graph,
)
from sdd_trainer.core.llm_manager import LLMManager
from sdd_trainer.core.memory import TrainingStateStore
from sdd_trainer.core.prompts import CALIBRATION_QUESTION
from sdd_trainer.lessons import load_quiz
from sdd_trainer.models import Assessment, DocsDecision, RepoAnalysis, RouteDecision

pytestmark = pytest.mark.unit

THREAD = {"configurable": {"thread_id": "student:unit"}}

#: A literal lesson text returned by the fake LLM — the graph must deliver
#: it to ``teach_output`` verbatim (independent truth, not recomputed).
LESSON_TEXT = (
    "# OpenSpec-основы — урок\n\n"
    "## Goal\nПонять specs/ и changes/.\n\n"
    "## Key concepts\n- specs/ — истина\n- changes/ — предложения\n"
)


# --- fake OpenAI client (the same seam as test_llm_manager, no network) ---

def _tool_call_response(tool_name: str, arguments: str) -> SimpleNamespace:
    """Build an openai-like completion whose message carries one tool call."""
    function = SimpleNamespace(name=tool_name, arguments=arguments)
    tool_call = SimpleNamespace(id="call_1", type="function", function=function)
    message = SimpleNamespace(content=None, tool_calls=[tool_call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _text_response(text: str) -> SimpleNamespace:
    """Build an openai-like plain-text completion (for ``LLMManager.complete``)."""
    message = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeOpenAI:
    """Stand-in for ``openai.OpenAI`` recording ``create()`` calls (test seam)."""

    def __init__(self, replies: list) -> None:
        self._replies = list(replies)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model: str, messages: list[dict], **kwargs) -> SimpleNamespace:
        self.calls.append({"model": model, "messages": messages, **kwargs})
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, str):
            return _text_response(reply)  # plain lesson text -> completion
        return reply


def _assessment_payload(
    level: str = "partial",
    confidence: float = 0.8,
    justification: str = "Знает про specs/, но путается в change proposals.",
) -> str:
    return json.dumps(
        {
            "domain": "openspec-basics",
            "level": level,
            "justification": justification,
            "confidence": confidence,
        },
        ensure_ascii=False,
    )


def _route_payload(path: str = "partial", reason: str = "Есть пробелы.") -> str:
    return json.dumps({"path": path, "reason": reason}, ensure_ascii=False)


def _docs_payload(
    needs_docs: bool = False,
    query: str = "",
    reason: str = "Скелета достаточно для полного урока.",
) -> str:
    """Valid DocsDecision tool-call arguments as a JSON string."""
    return json.dumps(
        {"needs_docs": needs_docs, "query": query, "reason": reason},
        ensure_ascii=False,
    )


def _teach_replies(
    level: str, docs: str | None = None, lesson: str = LESSON_TEXT
) -> list:
    """Fake replies for a confident session ending in the teach node.

    assessment -> route(level) -> docs decision -> lesson text. The docs
    reply defaults to "skeleton suffices" (no search).
    """
    return [
        _tool_call_response(
            "Assessment", _assessment_payload(level=level, confidence=0.9)
        ),
        _tool_call_response("RouteDecision", _route_payload(path=level)),
        _tool_call_response(
            "DocsDecision", docs if docs is not None else _docs_payload()
        ),
        lesson,
    ]


def _graph(
    replies: list,
    checkpointer=None,
    docs_search=None,
    state_store=None,
    repo_path=None,
    repo_analyzer=None,
) -> tuple:
    """Compile the trainer graph over a fake LLM client (no network).

    The training-state store defaults to a throwaway temp file: unit
    tests must never touch the repo's runtime ``data/training-state.json``
    (the quiz node writes through the store when a session completes).
    ``repo_path`` / ``repo_analyzer`` wire the passive analysis seam
    (task 3.1): tests inject a fake analyzer — the same external-
    collaborator discipline as ``docs_search``.
    """
    fake = FakeOpenAI(replies)
    llm = LLMManager(config=GigaChatConfig(api_key="test"), client=fake)
    if state_store is None:
        state_store = TrainingStateStore(
            path=Path(tempfile.mkdtemp()) / "training-state.json"
        )
    graph = build_graph(
        llm,
        checkpointer=checkpointer or InMemorySaver(),
        docs_search=docs_search,
        state_store=state_store,
        repo_path=repo_path,
        repo_analyzer=repo_analyzer,
    )
    return graph, fake


#: Canned passive-scan evidence (independent truth, literal — the graph must
#: deliver it to the prompt, the log, and the state verbatim).
RICH_ANALYSIS = RepoAnalysis(
    repo_path="/tmp/rich-repo",
    has_openspec=True,
    spec_domains=["console-trainer"],
    change_names=["add-console-trainer"],
    shall_count=4,
    scenario_count=2,
    summary=(
        "openspec/ активен: спецификации — console-trainer; "
        "активные changes — add-console-trainer; требований SHALL — 4; "
        "сценариев WHEN/THEN — 2"
    ),
)


class FakeAnalyzer:
    """Stand-in for ``analyze_student_repo`` at the graph seam (records calls)."""

    def __init__(self, analysis: RepoAnalysis = RICH_ANALYSIS, error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self._analysis = analysis
        self._error = error

    def __call__(self, repo_path: str) -> RepoAnalysis:
        self.calls.append(repo_path)
        if self._error is not None:
            raise self._error
        return self._analysis


def _start(graph, thread: dict = THREAD) -> dict:
    return graph.invoke({"domain": "openspec-basics"}, thread)


def _resume(graph, answer: str, thread: dict = THREAD) -> dict:
    return graph.invoke(Command(resume=answer), thread)


def _knows_it_replies() -> list:
    """Fake replies for a confident knows_it session: assessment + route.

    The quiz node is deterministic (no LLM judge) — no further replies.
    """
    return [
        _tool_call_response(
            "Assessment", _assessment_payload(level="knows_it", confidence=0.9)
        ),
        _tool_call_response("RouteDecision", _route_payload(path="knows_it")),
    ]


def _drive(graph, answers: list, thread: dict = THREAD) -> tuple:
    """Run a whole session, feeding each interrupt the next canned answer.

    Returns (final_state, asked_questions) — the interrupt payloads in the
    order the graph asked them (calibration question first, then quiz).
    """
    canned = list(answers)
    result = graph.invoke({"domain": "openspec-basics"}, thread)
    asked: list[str] = []
    while result.get("__interrupt__"):
        asked.append(result["__interrupt__"][0].value)
        result = graph.invoke(Command(resume=canned.pop(0)), thread)
    return result, asked


class TestAssessNode:
    """assess: calibration question via interrupt, then structured Assessment."""

    def test_first_invoke_interrupts_before_any_llm_call(self) -> None:
        graph, fake = _graph(replies=[])  # any LLM call would pop from an empty list

        result = _start(graph)

        assert result["__interrupt__"][0].value == CALIBRATION_QUESTION
        assert result["domain"] == "openspec-basics"
        assert fake.calls == []  # no completion before the student's answer

    def test_assessment_lands_in_state_and_log(self) -> None:
        graph, fake = _graph(
            [
                _tool_call_response("Assessment", _assessment_payload(level="partial", confidence=0.7)),
                _tool_call_response("RouteDecision", _route_payload(path="partial")),
                # partial -> teach: docs decision + lesson text
                _tool_call_response("DocsDecision", _docs_payload()),
                LESSON_TEXT,
            ]
        )

        _start(graph)
        result = _resume(graph, "мой ответ")

        assert result["assessment"]["level"] == "partial"
        assert result["calibration_answer"] == "мой ответ"
        assert result["clarification_rounds"] == 0
        assert any(entry.startswith("Оценка: partial") for entry in result["log"])
        assert fake.calls[0]["tools"][0]["function"]["name"] == "Assessment"

    def test_passive_repo_analysis_reaches_prompt_log_and_state(self) -> None:
        """Task 3.1 (issue #7): scan evidence → LLM call, session log, state."""
        analyzer = FakeAnalyzer()
        graph, fake = _graph(
            _knows_it_replies(),
            repo_path="/tmp/rich-repo",
            repo_analyzer=analyzer,
        )

        _start(graph)
        result = _resume(graph, "мой ответ")

        assert analyzer.calls == ["/tmp/rich-repo"]
        # evidence reached the structured assessment call (recorded at the seam)
        user_message = fake.calls[0]["messages"][-1]["content"]
        assert RICH_ANALYSIS.summary in user_message
        # the tool call is visible in the session log (course criterion 3)
        # and precedes the assessment verdict entry
        tool_entries = [
            i for i, e in enumerate(result["log"]) if e.startswith("Инструмент analyze_student_repo")
        ]
        assert tool_entries, result["log"]
        assert RICH_ANALYSIS.summary in result["log"][tool_entries[0]]
        verdict = next(
            i for i, e in enumerate(result["log"]) if e.startswith("Оценка:")
        )
        assert tool_entries[0] < verdict
        # the structured evidence lands in the graph state
        assert result["repo_analysis"]["has_openspec"] is True
        assert result["repo_analysis"]["shall_count"] == 4
        assert result["repo_analysis"]["summary"] == RICH_ANALYSIS.summary

    def test_no_repo_path_skips_passive_analysis(self) -> None:
        """Without a repo the assess node stays on the self-report only."""
        analyzer = FakeAnalyzer()
        graph, fake = _graph(
            [
                _tool_call_response("Assessment", _assessment_payload()),
                _tool_call_response("RouteDecision", _route_payload(path="partial")),
                _tool_call_response("DocsDecision", _docs_payload()),
                LESSON_TEXT,
            ],
            repo_analyzer=analyzer,  # wired but must not fire: no repo_path
        )

        _start(graph)
        result = _resume(graph, "мой ответ")

        assert analyzer.calls == []
        assert not any(
            "analyze_student_repo" in entry for entry in result["log"]
        )
        assert (
            "Анализ репозитория ученика"
            not in fake.calls[0]["messages"][-1]["content"]
        )
        assert result["repo_analysis"] == {}

    def test_analyzer_failure_degrades_to_self_assessment(self) -> None:
        """A scan failure must not kill the session — honest log, self-report."""
        analyzer = FakeAnalyzer(error=RuntimeError("scan failed"))
        graph, fake = _graph(
            [
                _tool_call_response(
                    "Assessment",
                    _assessment_payload(level="partial", confidence=0.7),
                ),
                _tool_call_response("RouteDecision", _route_payload(path="partial")),
                _tool_call_response("DocsDecision", _docs_payload()),
                LESSON_TEXT,
            ],
            repo_path="/tmp/broken-repo",
            repo_analyzer=analyzer,
        )

        _start(graph)
        result = _resume(graph, "мой ответ")

        assert any(
            "не смог проанализировать репозиторий (RuntimeError)" in entry
            for entry in result["log"]
        )
        assert result["assessment"]["level"] == "partial"  # session survived
        assert (
            "Анализ репозитория ученика"
            not in fake.calls[0]["messages"][-1]["content"]
        )
        assert result["repo_analysis"] == {}


class TestRoutingPaths:
    """route: exactly one of knows_it / partial / new_topic (+ clarification)."""

    @pytest.mark.parametrize(
        ("level", "path"),
        [
            ("knows_it", "knows_it"),
            ("partial", "partial"),
            ("new_topic", "new_topic"),
        ],
    )
    def test_confident_assessment_routes_via_llm_to_path(
        self, level: str, path: str
    ) -> None:
        replies = [
            _tool_call_response(
                "Assessment", _assessment_payload(level=level, confidence=0.9)
            ),
            _tool_call_response("RouteDecision", _route_payload(path=path)),
        ]
        if path != "knows_it":
            replies.extend(_teach_replies(level)[2:])  # docs decision + lesson
        graph, fake = _graph(replies)

        _start(graph)
        result = _resume(graph, "ответ ученика")

        assert result["route"]["path"] == path
        assert any(entry.startswith(f"Маршрут: {path}") for entry in result["log"])
        # every path now ends at the quiz (proposal topology: teach -> quiz)
        question = result["__interrupt__"][0].value
        assert question == load_quiz("openspec-basics").questions[0].question
        if path == "knows_it":
            assert not result["teach_output"]  # knows_it skips the lesson
        else:
            assert result["teach_output"] == LESSON_TEXT  # the lesson came first
        # the routing decision came through the structured-output seam (ADR-005)
        assert fake.calls[1]["tools"][0]["function"]["name"] == "RouteDecision"
        assert fake.calls[1]["tool_choice"]["function"]["name"] == "RouteDecision"

    def test_route_call_carries_the_assessment(self) -> None:
        graph, fake = _graph(_teach_replies("partial"))

        _start(graph)
        _resume(graph, "ответ")

        route_call = fake.calls[1]
        assert '"level": "partial"' in route_call["messages"][1]["content"]
        assert "Выбери путь обучения." in route_call["messages"][1]["content"]

    def test_low_confidence_routes_to_clarification_without_llm_call(self) -> None:
        """The clarification rule is deterministic: no route completion is spent."""
        graph, fake = _graph(
            [_tool_call_response("Assessment", _assessment_payload(confidence=0.2))]
        )

        _start(graph)
        result = _resume(graph, "противоречивый ответ")

        assert result["route"]["path"] == "clarification"
        assert len(fake.calls) == 1  # only the assessment call
        question = result["__interrupt__"][0].value
        assert "Уточни" in question  # the clarify node asks a follow-up

    def test_clarification_round_reassesses_and_routes(self) -> None:
        graph, fake = _graph(
            [
                _tool_call_response("Assessment", _assessment_payload(level="partial", confidence=0.2)),
                _tool_call_response("Assessment", _assessment_payload(level="knows_it", confidence=0.9)),
                _tool_call_response("RouteDecision", _route_payload(path="knows_it")),
            ]
        )

        _start(graph)
        result = _resume(graph, "калибровочный ответ")
        assert result["route"]["path"] == "clarification"

        result = _resume(graph, "уточняющий ответ")

        assert result["route"]["path"] == "knows_it"
        assert result["assessment"]["level"] == "knows_it"
        assert result["clarification_rounds"] == 1
        # knows_it -> the quiz asks its first question
        question = result["__interrupt__"][0].value
        assert question == load_quiz("openspec-basics").questions[0].question
        # the re-assessment saw the whole dialogue
        reassessment = fake.calls[1]["messages"][1]["content"]
        assert "калибровочный ответ" in reassessment
        assert "уточняющий ответ" in reassessment
        # both route decisions are visible in the session log
        assert sum("Маршрут: clarification" in entry for entry in result["log"]) == 1
        assert sum("Маршрут: knows_it" in entry for entry in result["log"]) == 1

    def test_max_clarification_rounds_bound_the_loop(self) -> None:
        """After MAX_CLARIFICATION_ROUNDS the graph follows the assessed level."""
        graph, fake = _graph(
            [
                _tool_call_response("Assessment", _assessment_payload(level="new_topic", confidence=0.2)),
                _tool_call_response("Assessment", _assessment_payload(level="new_topic", confidence=0.3)),
                _tool_call_response("Assessment", _assessment_payload(level="new_topic", confidence=0.2)),
                # the bounded route follows the level -> teach runs
                _tool_call_response("DocsDecision", _docs_payload()),
                LESSON_TEXT,
            ]
        )

        _start(graph)
        result = _resume(graph, "ответ 1")
        assert result["route"]["path"] == "clarification"
        result = _resume(graph, "ответ 2")
        assert result["route"]["path"] == "clarification"

        result = _resume(graph, "ответ 3")

        assert result["route"]["path"] == "new_topic"
        assert result["clarification_rounds"] == MAX_CLARIFICATION_ROUNDS
        assert result["teach_output"] == LESSON_TEXT
        assert len(fake.calls) == 5  # 3 assessments + docs decision + lesson
        # the bounded route taught, and the session now waits at the quiz
        question = result["__interrupt__"][0].value
        assert question == load_quiz("openspec-basics").questions[0].question


class TestCheckpoint:
    """Criterion 4: checkpoints are written; an interrupted session resumes."""

    def test_checkpoint_written_and_session_resumes(self) -> None:
        checkpointer = InMemorySaver()
        graph, _ = _graph(
            [
                _tool_call_response("Assessment", _assessment_payload(level="knows_it", confidence=0.9)),
                _tool_call_response("RouteDecision", _route_payload(path="knows_it")),
            ],
            checkpointer=checkpointer,
        )

        _start(graph)
        snapshot = graph.get_state(THREAD)

        assert snapshot.next == ("assess",)  # paused at the calibration question
        assert snapshot.values["domain"] == "openspec-basics"
        assert list(checkpointer.list(THREAD))  # a checkpoint exists (criterion 4)

        result = _resume(graph, "ответ")

        assert result["route"]["path"] == "knows_it"
        # the session advanced past assess/route and now waits at the quiz
        assert graph.get_state(THREAD).next == ("quiz",)
        question = result["__interrupt__"][0].value
        assert question == load_quiz("openspec-basics").questions[0].question

    def test_sqlite_checkpoint_survives_restart(self, tmp_path) -> None:
        """A fresh graph + connection on the same db file resumes the session."""
        db = tmp_path / "checkpoints.sqlite"

        def _open() -> SqliteSaver:
            return SqliteSaver(sqlite3.connect(db, check_same_thread=False))

        # session 1: the question is asked, the "process" ends without an answer
        graph1, _ = _graph(replies=[], checkpointer=_open())
        result = graph1.invoke({"domain": "openspec-basics"}, THREAD)
        assert "__interrupt__" in result

        # session 2: new graph instance, new connection — same db, same thread
        graph2, fake2 = _graph(
            [
                _tool_call_response("Assessment", _assessment_payload(level="knows_it", confidence=0.9)),
                _tool_call_response("RouteDecision", _route_payload(path="knows_it")),
            ],
            checkpointer=_open(),
        )
        snapshot = graph2.get_state(THREAD)
        assert snapshot.next == ("assess",)  # resumed from the checkpoint
        assert snapshot.values["domain"] == "openspec-basics"

        result = graph2.invoke(Command(resume="ответ после рестарта"), THREAD)

        assert result["route"]["path"] == "knows_it"
        assert result["calibration_answer"] == "ответ после рестарта"
        # resumed straight to the quiz (no LLM call needed there)
        assert graph2.get_state(THREAD).next == ("quiz",)
        assert len(fake2.calls) == 2

    def test_threads_are_isolated_per_student(self) -> None:
        graph, _ = _graph(_teach_replies("partial"))
        anna = {"configurable": {"thread_id": "student:anna"}}
        boris = {"configurable": {"thread_id": "student:boris"}}

        graph.invoke({"domain": "openspec-basics"}, anna)
        result = graph.invoke(Command(resume="ответ анны"), anna)
        assert result["route"]["path"] == "partial"

        # boris's thread is untouched — he starts from scratch
        boris_snapshot = graph.get_state(boris)
        assert boris_snapshot.next == ()
        assert boris_snapshot.values == {}

    def test_new_session_on_same_thread_resets_per_session_outputs(self) -> None:
        """Session 2 on the same thread must not inherit session 1's outputs."""
        quiz = load_quiz("openspec-basics")
        graph, _ = _graph(
            [
                # session 1: partial -> teach -> quiz (completed with refs)
                *_teach_replies("partial"),
                # session 2 (same thread): knows_it -> quiz again
                *_knows_it_replies(),
            ]
        )

        first, _ = _drive(
            graph, ["ответ первого сеанса", *[q.reference_answer for q in quiz.questions]]
        )
        assert first["teach_output"] == LESSON_TEXT
        assert first["quiz_result"]["passed"] is True

        # a fresh session on the same thread: assess resets per-session outputs
        second, _ = _drive(
            graph, ["ответ второго сеанса", *["абракадабра"] * len(quiz.questions)]
        )

        assert second["route"]["path"] == "knows_it"
        assert second["teach_output"] == ""  # reset by assess, not inherited
        assert second["quiz_result"]["passed"] is False  # this session's own quiz
        assert second["clarification_rounds"] == 0


class TestTeachNode:
    """teach: skeleton unfolding per level + search_sdd_docs on demand (T4).

    Task 3.3 (issue #5): the node loads the real lesson skeleton
    (ADR-009), asks through the structured seam whether the skeleton
    suffices, pulls fresh docs via the injected docs search when it does
    not, and unfolds the skeleton into a lesson under the assessed level.
    The level reaches the node from the assessment —
    ``state["assessment"]["level"]`` (T3 graph).
    """

    def test_unfolds_skeleton_into_lesson_and_logs_it(self) -> None:
        graph, fake = _graph(_teach_replies("new_topic"))

        _start(graph)
        result = _resume(graph, "ответ ученика")

        assert result["teach_output"] == LESSON_TEXT  # delivered verbatim
        assert any("Урок готов" in entry for entry in result["log"])
        # the docs decision went through the structured-output seam (ADR-005)
        docs_call = fake.calls[2]
        assert docs_call["tools"][0]["function"]["name"] == "DocsDecision"
        assert docs_call["tool_choice"]["function"]["name"] == "DocsDecision"
        # the docs decision saw the real skeleton and the level
        docs_content = docs_call["messages"][1]["content"]
        assert "## Key concepts" in docs_content
        assert "new_topic" in docs_content
        # the unfolding call is plain prose carrying the real skeleton
        unfold_call = fake.calls[3]
        assert "tools" not in unfold_call
        content = unfold_call["messages"][1]["content"]
        assert "## Key concepts" in content
        assert "## Quiz ref" in content
        assert "с нуля" in content  # the new_topic directive

    def test_level_and_gaps_reach_the_unfolding(self) -> None:
        """partial: the assessment justification steers the lesson (task 3.3)."""
        graph, fake = _graph(_teach_replies("partial"))

        _start(graph)
        _resume(graph, "ответ ученика")

        content = fake.calls[3]["messages"][1]["content"]
        assert "путается в change proposals" in content  # the justification
        assert "пробел" in content  # the partial directive

    def test_docs_needed_triggers_search_visible_in_the_log(self) -> None:
        """Spec scenario: the tool call and its results land in the session log."""
        searches: list[str] = []

        def fake_docs_search(query: str) -> list[dict]:
            searches.append(query)
            return [
                {
                    "title": "OpenSpec — workflow",
                    "url": "https://example.org/openspec-workflow",
                    "content": "explore → propose → apply → archive",
                }
            ]

        replies = _teach_replies(
            "new_topic",
            docs=_docs_payload(
                needs_docs=True,
                query="OpenSpec change proposal workflow",
                reason="Нужны свежие примеры workflow.",
            ),
        )
        graph, fake = _graph(replies, docs_search=fake_docs_search)

        _start(graph)
        result = _resume(graph, "ответ ученика")

        assert searches == ["OpenSpec change proposal workflow"]
        (tool_entry,) = [e for e in result["log"] if "search_sdd_docs" in e]
        assert "OpenSpec change proposal workflow" in tool_entry
        assert "https://example.org/openspec-workflow" in tool_entry
        # the fresh docs reached the unfolding prompt
        assert (
            "https://example.org/openspec-workflow"
            in fake.calls[3]["messages"][1]["content"]
        )
        assert result["teach_output"] == LESSON_TEXT

    def test_docs_sufficient_skips_the_search(self) -> None:
        searches: list[str] = []

        def fake_docs_search(query: str) -> list[dict]:
            searches.append(query)
            return []

        graph, _ = _graph(_teach_replies("new_topic"), docs_search=fake_docs_search)

        _start(graph)
        result = _resume(graph, "ответ ученика")

        assert searches == []
        assert not any("search_sdd_docs" in entry for entry in result["log"])

    def test_search_failure_does_not_kill_the_lesson(self) -> None:
        """A search outage degrades to a skeleton-only lesson, visibly."""

        def broken_docs_search(query: str) -> list[dict]:
            raise RuntimeError("TAVILY_API_KEY не задан")

        replies = _teach_replies(
            "new_topic",
            docs=_docs_payload(
                needs_docs=True, query="OpenSpec workflow", reason="Нужно больше.",
            ),
        )
        graph, _ = _graph(replies, docs_search=broken_docs_search)

        _start(graph)
        result = _resume(graph, "ответ ученика")

        assert result["teach_output"] == LESSON_TEXT
        (failure_entry,) = [
            e for e in result["log"] if "search_sdd_docs" in e
        ]
        assert "RuntimeError" in failure_entry  # type only, no payload
        assert "по скелету" in failure_entry

    def test_missing_query_falls_back_to_domain_default_search(self) -> None:
        """Live defect (demo 02.11): the model asked for docs but omitted the
        query — the node searches with the domain default instead of dying,
        and the fallback query is visible in the log."""
        searches: list[str] = []

        def fake_docs_search(query: str) -> list[dict]:
            searches.append(query)
            return [
                {
                    "title": "OpenSpec — workflow",
                    "url": "https://example.org/openspec-workflow",
                    "content": "explore → propose → apply → archive",
                }
            ]

        replies = _teach_replies(
            "new_topic",
            docs=_docs_payload(
                needs_docs=True, query="", reason="Нужны свежие примеры."
            ),
        )
        graph, _ = _graph(replies, docs_search=fake_docs_search)

        _start(graph)
        result = _resume(graph, "ответ ученика")

        assert searches == ["OpenSpec spec-driven development"]
        assert result["teach_output"] == LESSON_TEXT
        (tool_entry,) = [e for e in result["log"] if "search_sdd_docs" in e]
        assert "OpenSpec spec-driven development" in tool_entry

    def test_docs_decision_schema_is_the_structured_contract(self) -> None:
        schema = DocsDecision.model_json_schema()
        assert set(schema["properties"]) == {"needs_docs", "query", "reason"}


class TestGraphDefaults:
    """The routing policy constants are the documented course values."""

    def test_threshold_and_rounds(self) -> None:
        assert CLARIFICATION_THRESHOLD == 0.5
        assert MAX_CLARIFICATION_ROUNDS == 2

    def test_route_decision_schema_covers_all_paths(self) -> None:
        schema = RouteDecision.model_json_schema()
        assert set(schema["properties"]["path"]["enum"]) == {
            "knows_it",
            "partial",
            "new_topic",
            "clarification",
        }


class TestQuizNode:
    """quiz: JSON-quiz questions via interrupts, deterministic F1, state.

    Task 3.4 + 4.2 at the graph seam (issue #6). The real authored quiz
    (data/quizzes/openspec-basics.json, 5 questions, weights
    [1, 1, 1, 1.5, 1] — asserted as literals in test_lessons) drives the
    node; expected scores below are derived by hand from those weights,
    never recomputed with the implementation's code (anti-tautology).
    """

    @staticmethod
    def _store(tmp_path) -> TrainingStateStore:
        return TrainingStateStore(path=tmp_path / "training-state.json")

    def test_knows_it_session_reaches_quiz_and_scores_full(self, tmp_path) -> None:
        quiz = load_quiz("openspec-basics")
        graph, _ = _graph(_knows_it_replies(), state_store=self._store(tmp_path))

        result, asked = _drive(
            graph,
            ["работаю с openspec", *[q.reference_answer for q in quiz.questions]],
        )

        assert asked[0] == CALIBRATION_QUESTION
        assert asked[1:] == [q.question for q in quiz.questions]
        quiz_result = result["quiz_result"]
        assert quiz_result["domain"] == "openspec-basics"
        assert quiz_result["score"] == pytest.approx(1.0)  # exact references
        assert quiz_result["passed"] is True
        entry = self._store(tmp_path).load()["domains"]["openspec-basics"]
        assert entry == {"score": 1.0, "streak": 1, "completed_lessons": 1}

    def test_disjoint_answers_score_zero_and_fail(self, tmp_path) -> None:
        quiz = load_quiz("openspec-basics")
        graph, _ = _graph(_knows_it_replies(), state_store=self._store(tmp_path))

        result, asked = _drive(graph, ["ответ", *["абракадабра"] * len(quiz.questions)])

        assert len(asked) == 1 + len(quiz.questions)
        assert result["quiz_result"]["score"] == pytest.approx(0.0)
        assert result["quiz_result"]["passed"] is False
        entry = self._store(tmp_path).load()["domains"]["openspec-basics"]
        assert entry == {"score": 0.0, "streak": 0, "completed_lessons": 0}

    def test_weighted_score_at_the_seam(self, tmp_path) -> None:
        """Only q4 (weight 1.5 of 5.5 total) answered exactly -> 3/11."""
        quiz = load_quiz("openspec-basics")
        answers = ["абракадабра"] * len(quiz.questions)
        answers[3] = quiz.questions[3].reference_answer
        graph, _ = _graph(_knows_it_replies(), state_store=self._store(tmp_path))

        result, _ = _drive(graph, ["ответ", *answers])

        assert result["quiz_result"]["score"] == pytest.approx(1.5 / 5.5)
        assert result["quiz_result"]["passed"] is False  # 0.27 < 0.60

    def test_teach_flows_into_quiz(self, tmp_path) -> None:
        """partial route: lesson first, then the quiz (proposal topology)."""
        quiz = load_quiz("openspec-basics")
        graph, _ = _graph(
            _teach_replies("partial"), state_store=self._store(tmp_path)
        )

        result, asked = _drive(
            graph,
            ["частично знаком", *[q.reference_answer for q in quiz.questions]],
        )

        assert result["teach_output"] == LESSON_TEXT
        assert result["quiz_result"]["passed"] is True
        log = result["log"]
        lesson_at = next(i for i, e in enumerate(log) if e.startswith("Урок готов"))
        quiz_at = next(
            i for i, e in enumerate(log) if e.startswith("Проверка знаний")
        )
        assert lesson_at < quiz_at

    def test_training_state_survives_restart_and_tracks_streak(
        self, tmp_path
    ) -> None:
        """Passed quiz -> streak 1; restart (new store) sees it; a failed
        second session resets the streak and keeps completed_lessons."""
        quiz = load_quiz("openspec-basics")
        graph, _ = _graph(
            _knows_it_replies() + _knows_it_replies(),
            state_store=self._store(tmp_path),
        )

        _drive(graph, ["ответ", *[q.reference_answer for q in quiz.questions]])
        entry = self._store(tmp_path).load()["domains"]["openspec-basics"]
        assert entry == {"score": 1.0, "streak": 1, "completed_lessons": 1}

        result, _ = _drive(
            graph, ["ответ", *["абракадабра"] * len(quiz.questions)]
        )
        assert result["quiz_result"]["passed"] is False
        entry = self._store(tmp_path).load()["domains"]["openspec-basics"]
        assert entry == {"score": 0.0, "streak": 0, "completed_lessons": 1}
