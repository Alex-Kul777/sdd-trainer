"""Unit tests for the console session glue helpers (task 6.1, thin glue).

Only the pure helpers are unit-tested: the thread-id convention, the
pending-question extraction from a checkpoint snapshot, and the session
summary formatting. The interactive loop itself is manual smoke
(design.md: «Консоль — тонкий клей, ручной смоук»).
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from sdd_trainer.config import GigaChatConfig
from sdd_trainer.core.graph import build_graph
from sdd_trainer.core.llm_manager import LLMManager
from sdd_trainer.core.memory import TrainingStateStore
from sdd_trainer.__main__ import (
    DEFAULT_STUDENT,
    find_pending_question,
    format_session_summary,
    has_pending_session,
    student_thread_id,
)

pytestmark = pytest.mark.unit

THREAD = {"configurable": {"thread_id": "student:glue"}}


class _FakeOpenAI:
    """Fake client with scripted tool-call replies (same seam as test_graph)."""

    def __init__(self, replies: list | None = None) -> None:
        self._replies = list(replies or [])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model: str, messages: list, **kwargs):
        if not self._replies:
            raise AssertionError("unexpected LLM call: no scripted reply left")
        reply = self._replies.pop(0)
        if "text" in reply:
            # plain prose completion (the teach lesson, LLMManager.complete)
            message = SimpleNamespace(content=reply["text"], tool_calls=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])
        function = SimpleNamespace(name=reply["tool"], arguments=reply["arguments"])
        tool_call = SimpleNamespace(id="call_1", type="function", function=function)
        message = SimpleNamespace(content=None, tool_calls=[tool_call])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _assessment_arguments() -> str:
    import json

    return json.dumps(
        {
            "domain": "openspec-basics",
            "level": "partial",
            "justification": "Есть пробелы.",
            "confidence": 0.8,
        },
        ensure_ascii=False,
    )


def _route_arguments() -> str:
    import json

    return json.dumps({"path": "partial", "reason": "Нужен разбор."}, ensure_ascii=False)


def _docs_arguments() -> str:
    import json

    return json.dumps(
        {"needs_docs": False, "query": "", "reason": "Скелета достаточно."},
        ensure_ascii=False,
    )


def _graph(replies: list | None = None):
    """Graph over a fake client; a completed session needs both replies.

    The training-state store points at a throwaway temp file: unit tests
    must never touch the repo's runtime ``data/training-state.json``.
    """
    return build_graph(
        LLMManager(config=GigaChatConfig(api_key="test"), client=_FakeOpenAI(replies)),
        checkpointer=InMemorySaver(),
        state_store=TrainingStateStore(
            path=Path(tempfile.mkdtemp()) / "training-state.json"
        ),
    )


class TestStudentThreadId:
    """thread_id follows the ADR-008 convention: student:<name>."""

    def test_builds_convention_id(self) -> None:
        assert student_thread_id("alex") == "student:alex"
        assert student_thread_id("  maria  ") == "student:maria"

    def test_rejects_empty_and_multi_token_names(self) -> None:
        with pytest.raises(ValueError):
            student_thread_id("")
        with pytest.raises(ValueError):
            student_thread_id("   ")
        with pytest.raises(ValueError):
            student_thread_id("alex smith")

    def test_default_student_matches_adr008_example(self) -> None:
        assert DEFAULT_STUDENT == "alex"
        assert student_thread_id(DEFAULT_STUDENT) == "student:alex"


class TestFindPendingQuestion:
    """find_pending_question: the interrupt payload out of a snapshot."""

    def test_returns_calibration_question_while_paused(self) -> None:
        graph = _graph()
        graph.invoke({"domain": "openspec-basics"}, THREAD)

        snapshot = graph.get_state(THREAD)
        assert snapshot.next == ("assess",)
        assert find_pending_question(snapshot) is not None
        assert "OpenSpec" in find_pending_question(snapshot)

    def test_returns_none_when_session_completed(self) -> None:
        from sdd_trainer.lessons import load_quiz

        graph = _graph(
            [
                {"tool": "Assessment", "arguments": _assessment_arguments()},
                {"tool": "RouteDecision", "arguments": _route_arguments()},
                # partial -> teach (T4): docs decision + lesson text
                {"tool": "DocsDecision", "arguments": _docs_arguments()},
                {"text": "# Урок OpenSpec-основы"},
            ]
        )
        done = {"configurable": {"thread_id": "student:glue-done"}}
        graph.invoke({"domain": "openspec-basics"}, done)
        result = graph.invoke(Command(resume="ответ"), done)

        # teach now flows into the quiz (T5): answer every question to
        # complete the session — the quiz itself needs no scripted replies
        # (deterministic F1, no LLM judge)
        quiz_answers = iter(
            ["эталонный ответ"] * len(load_quiz("openspec-basics").questions)
        )
        while result.get("__interrupt__"):
            result = graph.invoke(Command(resume=next(quiz_answers)), done)

        snapshot = graph.get_state(done)
        assert snapshot.next == ()
        assert find_pending_question(snapshot) is None

    def test_returns_none_on_fresh_thread(self) -> None:
        graph = _graph()

        snapshot = graph.get_state(THREAD)
        assert snapshot.next == ()
        assert find_pending_question(snapshot) is None


class TestHasPendingSession:
    """has_pending_session: the resume gate must see every pause shape.

    Regression (live smoke 03.11, issue #8): after the first resume cycle
    LangGraph leaves ``snapshot.next`` empty while the task still holds a
    pending interrupt. A mid-quiz pause (question 2+) must still be
    detected as resumable — gating on ``snapshot.next`` alone made the
    console start a fresh session and lose the student's answers.
    """

    def test_fresh_thread_has_no_pending_session(self) -> None:
        graph = _graph()

        assert has_pending_session(graph.get_state(THREAD)) is False

    def test_calibration_pause_is_pending(self) -> None:
        graph = _graph()
        graph.invoke({"domain": "openspec-basics"}, THREAD)

        assert has_pending_session(graph.get_state(THREAD)) is True

    def test_mid_quiz_pause_is_pending(self) -> None:
        graph = _graph(
            [
                {"tool": "Assessment", "arguments": _assessment_arguments()},
                {"tool": "RouteDecision", "arguments": _route_arguments()},
                {"tool": "DocsDecision", "arguments": _docs_arguments()},
                {"text": "# Урок OpenSpec-основы"},
            ]
        )
        mid = {"configurable": {"thread_id": "student:glue-midquiz"}}
        graph.invoke({"domain": "openspec-basics"}, mid)
        # through assess -> route -> teach; paused at quiz q1
        result = graph.invoke(Command(resume="ответ"), mid)
        assert result.get("__interrupt__")
        # answer q1 and q2 -> paused at q3: next is empty, interrupt pending
        graph.invoke(Command(resume="ответ 1"), mid)
        graph.invoke(Command(resume="ответ 2"), mid)

        snapshot = graph.get_state(mid)
        assert snapshot.next == ()  # the LangGraph pause shape that broke the gate
        assert find_pending_question(snapshot) is not None
        assert has_pending_session(snapshot) is True

    def test_completed_session_is_not_pending(self) -> None:
        from sdd_trainer.lessons import load_quiz

        graph = _graph(
            [
                {"tool": "Assessment", "arguments": _assessment_arguments()},
                {"tool": "RouteDecision", "arguments": _route_arguments()},
                {"tool": "DocsDecision", "arguments": _docs_arguments()},
                {"text": "# Урок OpenSpec-основы"},
            ]
        )
        done = {"configurable": {"thread_id": "student:glue-done2"}}
        graph.invoke({"domain": "openspec-basics"}, done)
        result = graph.invoke(Command(resume="ответ"), done)
        answers = iter(
            ["эталонный ответ"] * len(load_quiz("openspec-basics").questions)
        )
        while result.get("__interrupt__"):
            result = graph.invoke(Command(resume=next(answers)), done)

        assert has_pending_session(graph.get_state(done)) is False


class TestFormatSessionSummary:
    """format_session_summary: renders the final state (pure function)."""

    def test_full_state_renders_level_route_and_stubs(self) -> None:
        state = {
            "domain": "openspec-basics",
            "assessment": {
                "level": "partial",
                "confidence": 0.7,
                "justification": "Есть пробелы.",
            },
            "route": {"path": "partial", "reason": "Нужен разбор."},
            "teach_output": "[teach/stub] Урок…",
            "clarification_rounds": 1,
        }

        lines = format_session_summary(state, "alex", "student:alex")
        text = "\n".join(lines)

        assert "Ученик: alex (thread_id: student:alex)" in text
        assert "Домен: openspec-basics" in text
        assert "Уровень: partial (уверенность 0.70)" in text
        assert "Обоснование: Есть пробелы." in text
        assert "Маршрут: partial — Нужен разбор." in text
        assert "Урок: [teach/stub] Урок…" in text
        assert "Уточняющих вопросов за сеанс: 1" in text
        assert "Чекпоинт сохранён" in text

    def test_minimal_state_renders_gracefully(self) -> None:
        lines = format_session_summary({}, "maria", "student:maria")
        text = "\n".join(lines)

        assert "Домен: —" in text
        assert "Уровень:" not in text
        assert "Маршрут:" not in text
        assert "Уточняющих" not in text

    def test_quiz_state_renders_quiz_line(self) -> None:
        state = {
            "domain": "openspec-basics",
            "assessment": {"level": "knows_it", "confidence": 0.9, "justification": ""},
            "route": {"path": "knows_it", "reason": "Веду на квиз."},
            "quiz_output": "[quiz/stub] Квиз…",
        }

        text = "\n".join(format_session_summary(state, "alex", "student:alex"))

        assert "Квиз: [quiz/stub] Квиз…" in text
        assert "Урок:" not in text

    def test_progress_renders_training_state_score(self) -> None:
        """Score comes from training-state.json (progress), not the graph state.

        Task 7.3 (issue #8): the summary must show the persisted score —
        the checkpoint state may be gone while training-state survives.
        """
        state = {
            "domain": "openspec-basics",
            "quiz_result": {
                "domain": "openspec-basics",
                "score": 0.83,
                "passed": True,
                "feedback": "Хорошо!",
            },
        }
        progress = {"score": 0.83, "streak": 1, "completed_lessons": 1}

        text = "\n".join(
            format_session_summary(
                state, "alex", "student:alex", progress=progress
            )
        )

        assert (
            "Прогресс (training-state.json): счёт 0.83, серия 1, "
            "уроков завершено 1" in text
        )

    def test_passed_quiz_advises_next_domain(self) -> None:
        state = {
            "domain": "openspec-basics",
            "quiz_result": {
                "domain": "openspec-basics",
                "score": 0.9,
                "passed": True,
                "feedback": "Отлично",
            },
        }

        text = "\n".join(format_session_summary(state, "alex", "student:alex"))

        assert "Что дальше:" in text
        assert "квиз зачтён" in text
        assert "следующему домену" in text

    def test_failed_quiz_advises_retry(self) -> None:
        state = {
            "domain": "openspec-basics",
            "quiz_result": {
                "domain": "openspec-basics",
                "score": 0.2,
                "passed": False,
                "feedback": "Повтори",
            },
        }

        text = "\n".join(format_session_summary(state, "alex", "student:alex"))

        assert "Что дальше:" in text
        assert "квиз не зачтён" in text
        assert "--student" in text

    def test_no_quiz_advises_continuing(self) -> None:
        text = "\n".join(format_session_summary({}, "maria", "student:maria"))

        assert "Что дальше:" in text
        assert "не дошёл до квиза" in text

    def test_without_progress_no_score_line(self) -> None:
        state = {"domain": "openspec-basics"}

        text = "\n".join(format_session_summary(state, "alex", "student:alex"))

        assert "Прогресс (training-state.json)" not in text
