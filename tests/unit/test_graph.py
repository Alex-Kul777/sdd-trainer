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
from sdd_trainer.core.prompts import CALIBRATION_QUESTION
from sdd_trainer.models import Assessment, DocsDecision, RouteDecision

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


def _graph(replies: list, checkpointer=None, docs_search=None) -> tuple:
    """Compile the trainer graph over a fake LLM client (no network)."""
    fake = FakeOpenAI(replies)
    llm = LLMManager(config=GigaChatConfig(api_key="test"), client=fake)
    graph = build_graph(
        llm, checkpointer=checkpointer or InMemorySaver(), docs_search=docs_search
    )
    return graph, fake


def _start(graph, thread: dict = THREAD) -> dict:
    return graph.invoke({"domain": "openspec-basics"}, thread)


def _resume(graph, answer: str, thread: dict = THREAD) -> dict:
    return graph.invoke(Command(resume=answer), thread)


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


class TestRoutingPaths:
    """route: exactly one of knows_it / partial / new_topic (+ clarification)."""

    @pytest.mark.parametrize(
        ("level", "path", "stub_key"),
        [
            ("knows_it", "knows_it", "quiz_output"),
            ("partial", "partial", "teach_output"),
            ("new_topic", "new_topic", "teach_output"),
        ],
    )
    def test_confident_assessment_routes_via_llm_to_path(
        self, level: str, path: str, stub_key: str
    ) -> None:
        replies = [
            _tool_call_response(
                "Assessment", _assessment_payload(level=level, confidence=0.9)
            ),
            _tool_call_response("RouteDecision", _route_payload(path=path)),
        ]
        if stub_key == "teach_output":
            replies.extend(_teach_replies(level)[2:])  # docs decision + lesson
        graph, fake = _graph(replies)

        _start(graph)
        result = _resume(graph, "ответ ученика")

        assert result["route"]["path"] == path
        assert result[stub_key]  # the path's node ran
        other = "quiz_output" if stub_key == "teach_output" else "teach_output"
        assert not result.get(other)  # …and only that one
        assert any(entry.startswith(f"Маршрут: {path}") for entry in result["log"])
        assert "__interrupt__" not in result
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
        assert result["quiz_output"]  # knows_it → quiz stub
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
        assert "__interrupt__" not in result


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

        assert graph.get_state(THREAD).next == ()  # session completed
        assert result["route"]["path"] == "knows_it"

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
        assert result["quiz_output"]
        assert graph2.get_state(THREAD).next == ()
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
        """Session 2 on the same thread must not inherit session 1's lesson."""
        graph, _ = _graph(
            [
                # session 1: partial -> teach (docs decision + lesson)
                *_teach_replies("partial"),
                # session 2 (same thread): knows_it -> quiz stub
                _tool_call_response("Assessment", _assessment_payload(level="knows_it", confidence=0.9)),
                _tool_call_response("RouteDecision", _route_payload(path="knows_it")),
            ]
        )

        _start(graph)
        first = _resume(graph, "ответ первого сеанса")
        assert first["teach_output"] == LESSON_TEXT

        _start(graph)  # a fresh session on the same thread
        second = _resume(graph, "ответ второго сеанса")

        assert second["route"]["path"] == "knows_it"
        assert second["quiz_output"]
        assert second["teach_output"] == ""  # reset by assess, not inherited
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
