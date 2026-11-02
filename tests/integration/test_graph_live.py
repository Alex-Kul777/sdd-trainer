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
from sdd_trainer.core.prompts import CALIBRATION_QUESTION

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


def _live_graph(checkpointer) -> object:
    """Compile the trainer graph against the real GigaChat endpoint."""
    return build_graph(
        LLMManager(config=GigaChatConfig()), checkpointer=checkpointer
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
    assert result["teach_output"]  # new_topic → teach stub
    assert not result.get("quiz_output")
    assert any(
        entry.startswith("Маршрут: new_topic") for entry in result["log"]
    )  # criterion 5: the route is visible in the session log
    assert graph.get_state(thread).next == ()


@requires_key
def test_knowledgeable_student_skips_to_quiz_or_targeted_lesson_live() -> None:
    """WHEN a knowledgeable student is assessed THEN the route skips the full lecture."""
    graph = _live_graph(InMemorySaver())
    thread = {"configurable": {"thread_id": "student:live-pro"}}

    graph.invoke({"domain": "openspec-basics"}, thread)
    result = graph.invoke(Command(resume=KNOWLEDGEABLE_ANSWER), thread)

    assert result["assessment"]["level"] in {"knows_it", "partial"}
    assert result["route"]["path"] in {"knows_it", "partial"}
    # exactly one stub ran: knows_it → quiz, partial → teach (the other
    # channel was never written, hence .get())
    assert bool(result.get("teach_output")) != bool(result.get("quiz_output"))
    assert any(entry.startswith("Маршрут:") for entry in result["log"])
    assert graph.get_state(thread).next == ()


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
    assert graph2.get_state(thread).next == ()
