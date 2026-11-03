"""Unit tests for the console session glue helpers (task 6.1, thin glue).

Only the pure helpers are unit-tested: the thread-id convention, the
pending-question extraction from a checkpoint snapshot, and the session
summary formatting. The interactive loop itself is manual smoke
(design.md: «Консоль — тонкий клей, ручной смоук»).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from sdd_trainer.config import GigaChatConfig
from sdd_trainer.core.graph import build_graph
from sdd_trainer.core.llm_manager import LLMManager
from sdd_trainer.__main__ import (
    DEFAULT_STUDENT,
    find_pending_question,
    format_session_summary,
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
    """Graph over a fake client; a completed session needs both replies."""
    return build_graph(
        LLMManager(config=GigaChatConfig(api_key="test"), client=_FakeOpenAI(replies)),
        checkpointer=InMemorySaver(),
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
