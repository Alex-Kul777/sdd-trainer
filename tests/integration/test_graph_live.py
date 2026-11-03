"""Integration tests: the trainer graph with real GigaChat (issue #4, task 7.2).

The seam is the same as in the unit tests (design.md) — the graph boundary —
but wired to the live cloud.ru endpoint. Skipped unless ``GIGACHAT_KEY`` is
set (locally the git-ignored ``.env`` provides it; CI without the secret
skips). Asserts stay on external behavior: the selected route, the session
log, and the checkpoint surviving a restart (criterion 4).
"""
from __future__ import annotations

import os
import sqlite3

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from sdd_trainer.config import GigaChatConfig
from sdd_trainer.core.graph import build_graph
from sdd_trainer.core.llm_manager import LLMManager
from sdd_trainer.core.memory import TrainingStateStore
from sdd_trainer.core.prompts import CALIBRATION_QUESTION
from sdd_trainer.lessons import load_quiz

pytestmark = pytest.mark.integration

requires_key = pytest.mark.skipif(
    not os.getenv("GIGACHAT_KEY"),
    reason="GIGACHAT_KEY not set — live GigaChat tests skipped (see .env.example)",
)

NEWCOMER_ANSWER = (
    "Честно говоря, впервые слышу про OpenSpec и не знаю, что это такое."
)

KNOWLEDGEABLE_ANSWER = (
    "OpenSpec — инструмент spec-driven development. В specs/ лежат стабильные "
    "спецификации требований (source of truth), в changes/ — change proposals: "
    "предложения изменений с proposal.md, design.md, tasks.md и дельтой спеки. "
    "Proposal проходит review, применяется и архивируется, а спецификация "
    "остаётся источником истины."
)


def _live_graph(checkpointer, state_store=None) -> object:
    """Compile the trainer graph against the real GigaChat endpoint.

    The training-state store defaults to a throwaway temp file — live
    tests must not write into the repo's runtime training-state.json.
    """
    import tempfile
    from pathlib import Path

    if state_store is None:
        state_store = TrainingStateStore(
            path=Path(tempfile.mkdtemp()) / "training-state.json"
        )
    return build_graph(
        LLMManager(config=GigaChatConfig()),
        checkpointer=checkpointer,
        state_store=state_store,
    )


@requires_key
def test_newcomer_full_session_routes_to_new_topic_live() -> None:
    """WHEN a newcomer completes a session THEN the route is new_topic and visible in the log."""
    graph = _live_graph(InMemorySaver())
    thread = {"configurable": {"thread_id": "student:live-newcomer"}}

    result = graph.invoke({"domain": "openspec-basics"}, thread)

    assert result["__interrupt__"][0].value == CALIBRATION_QUESTION

    result = graph.invoke(Command(resume=NEWCOMER_ANSWER), thread)

    assert result["assessment"]["level"] == "new_topic"
    assert result["route"]["path"] == "new_topic"
    assert result["teach_output"]  # new_topic → the real lesson ran
    assert not result.get("quiz_output")  # the quiz has not been answered yet
    assert any(
        entry.startswith("Маршрут: new_topic") for entry in result["log"]
    )  # criterion 5: the route is visible in the session log
    # teach flows into the quiz (T5): the session waits at the first question
    assert result["__interrupt__"][0].value == (
        load_quiz("openspec-basics").questions[0].question
    )
    assert graph.get_state(thread).next == ("quiz",)


@requires_key
def test_newcomer_lesson_is_real_not_stub_live() -> None:
    """WHEN a newcomer session reaches teach THEN the lesson is a real unfolded
    lesson (T4, task 3.3) — not the T3 stub — with the docs decision visible
    in the session log."""
    graph = _live_graph(InMemorySaver())
    thread = {"configurable": {"thread_id": "student:live-lesson"}}

    graph.invoke({"domain": "openspec-basics"}, thread)
    result = graph.invoke(Command(resume=NEWCOMER_ANSWER), thread)

    assert result["route"]["path"] == "new_topic"
    lesson = result["teach_output"]
    assert "[teach/stub]" not in lesson  # the T3 stub marker is gone
    assert len(lesson) > 400  # a real unfolded lesson, not a one-liner
    lowered = lesson.lower()
    # the lesson unfolds the skeleton's key concepts (OpenSpec structure)
    assert "openspec" in lowered or "спецификац" in lowered
    assert "specs" in lowered or "changes" in lowered
    # the docs decision and the finished lesson are visible in the log
    assert any(entry.startswith("Материалы:") for entry in result["log"])
    assert any("Урок готов" in entry for entry in result["log"])
    # the lesson is followed by the quiz (T5 topology)
    assert graph.get_state(thread).next == ("quiz",)


@requires_key
def test_knowledgeable_student_skips_to_quiz_or_targeted_lesson_live() -> None:
    """WHEN a knowledgeable student is assessed THEN the route skips the full lecture."""
    graph = _live_graph(InMemorySaver())
    thread = {"configurable": {"thread_id": "student:live-pro"}}

    graph.invoke({"domain": "openspec-basics"}, thread)
    result = graph.invoke(Command(resume=KNOWLEDGEABLE_ANSWER), thread)

    assert result["assessment"]["level"] in {"knows_it", "partial"}
    path = result["route"]["path"]
    assert path in {"knows_it", "partial"}
    # every path now ends at the quiz (T5): the first question is pending
    assert result["__interrupt__"][0].value == (
        load_quiz("openspec-basics").questions[0].question
    )
    assert graph.get_state(thread).next == ("quiz",)
    if path == "knows_it":
        assert not result["teach_output"]  # the full lecture was skipped
    else:
        assert result["teach_output"]  # partial got a targeted lesson first
    assert any(entry.startswith("Маршрут:") for entry in result["log"])


@requires_key
def test_sqlite_checkpoint_survives_restart_live(tmp_path) -> None:
    """WHEN the 'process' restarts mid-session THEN the new graph resumes from the checkpoint."""
    db = tmp_path / "checkpoints.sqlite"

    def _open() -> SqliteSaver:
        return SqliteSaver(sqlite3.connect(db, check_same_thread=False))

    # session 1: the question is asked; the "process" ends without an answer
    graph1 = _live_graph(_open())
    thread = {"configurable": {"thread_id": "student:live-restart"}}
    result = graph1.invoke({"domain": "openspec-basics"}, thread)
    assert "__interrupt__" in result

    # session 2: fresh graph instance + fresh connection on the same db file
    graph2 = _live_graph(_open())
    snapshot = graph2.get_state(thread)
    assert snapshot.next == ("assess",)  # resumed from the checkpoint
    assert snapshot.values["domain"] == "openspec-basics"

    result = graph2.invoke(Command(resume=NEWCOMER_ANSWER), thread)

    assert result["calibration_answer"] == NEWCOMER_ANSWER
    assert result["route"]["path"] == "new_topic"
    # resumed through teach, now waiting at the quiz (T5)
    assert graph2.get_state(thread).next == ("quiz",)
