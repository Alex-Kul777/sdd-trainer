"""Persistence for the trainer (criterion 4, AIA_04, ADR-008).

Two layers:

- LangGraph checkpointer — ``SqliteSaver`` at ``data/checkpoints.sqlite``
  with the per-student thread id ``student:<name>`` (ADR-008; InMemorySaver
  in unit tests only). Implemented in T3 (issue #4, task 4.1): an
  interrupted session resumes from the checkpoint on the next run.
- training state — ``data/training-state.json``: per-domain progress
  (domain, score, streak) across the 6 SDD domains (openclaw-tutor
  pattern). Task 4.2 (ticket T5, issue #6): :class:`TrainingStateStore`
  owns the file; the quiz node records results through it, and
  ``MemoryManager`` exposes load/save for the transports.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from langgraph.checkpoint.sqlite import SqliteSaver

from sdd_trainer.config import trainer_config


class TrainingStateStore:
    """File-backed ``data/training-state.json`` (ADR-008, task 4.2).

    The state is a plain dict keyed by domain —
    ``{"domains": {<domain>: {"score", "streak", "completed_lessons"}}}``
    (the ``DomainProgress`` fields, models.py). Update policy
    (``record_quiz_result``): the score always reflects the latest quiz;
    a passed quiz grows the streak and completes a lesson, a failed one
    resets the streak and leaves the completed count alone. The file is a
    runtime artifact (git-ignored like the checkpoint database).
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        """Store the state file path (defaults to ``TrainerConfig``)."""
        self.path = Path(path or trainer_config.training_state_path)

    def load(self) -> dict:
        """Return the persisted state, or a fresh one for a new student.

        Raises:
            ValueError: the file exists but is not valid JSON — a corrupt
                progress file must fail loudly, not silently reset the
                student's progress.
        """
        if not self.path.exists():
            return {"domains": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, state: dict) -> None:
        """Persist the state atomically enough for a console trainer."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def record_quiz_result(
        self, domain: str, score: float, passed: bool
    ) -> dict:
        """Update the domain's progress with a scored quiz and persist it.

        Args:
            domain: the quiz domain, e.g. ``openspec-basics``.
            score: the latest weighted quiz score (0..1).
            passed: the quiz verdict against the authored pass threshold.

        Returns:
            The updated domain entry
            (``{"score", "streak", "completed_lessons"}``).
        """
        state = self.load()
        domains = state.setdefault("domains", {})
        entry = domains.setdefault(
            domain, {"score": 0.0, "streak": 0, "completed_lessons": 0}
        )
        entry["score"] = score
        if passed:
            entry["streak"] += 1
            entry["completed_lessons"] += 1
        else:
            entry["streak"] = 0
        domains[domain] = entry
        self.save(state)
        return dict(entry)


class MemoryManager:
    """Checkpointer + training-state persistence (ADR-008).

    The sqlite connection is opened lazily — importing or instantiating the
    class never touches the filesystem. It is opened with
    ``check_same_thread=False`` because LangGraph writes checkpoints from
    background threads (verified against langgraph 1.1.6 /
    langgraph-checkpoint-sqlite 3.1.3). The database file is a runtime
    artifact and is git-ignored (``data/*.sqlite``).
    """

    def __init__(
        self,
        thread_id: str = "student:alex",
        checkpoint_path: Optional[Path] = None,
        training_state_path: Optional[Path] = None,
    ) -> None:
        """Store the student thread id and the persistence paths.

        Args:
            thread_id: LangGraph thread id of the student — the ADR-008
                convention is ``student:<name>`` (default: ``student:alex``).
            checkpoint_path: sqlite database for the SqliteSaver checkpointer;
                defaults to ``TrainerConfig.checkpoint_path``
                (``data/checkpoints.sqlite``).
            training_state_path: JSON file for the training state; defaults
                to ``TrainerConfig.training_state_path``
                (``data/training-state.json``).
        """
        self.thread_id = thread_id
        self.checkpoint_path = Path(
            checkpoint_path or trainer_config.checkpoint_path
        )
        self.training_state_path = Path(
            training_state_path or trainer_config.training_state_path
        )
        self._checkpointer: Optional[SqliteSaver] = None
        self._conn: Optional[sqlite3.Connection] = None

    def get_checkpointer(self) -> SqliteSaver:
        """Return the SqliteSaver checkpointer, creating it on first use.

        Creates the parent directory and the database file if needed. The
        same instance is returned on every call; call :meth:`close` to
        release the connection (the file stays on disk — that is the point
        of criterion 4).
        """
        if self._checkpointer is None:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                self.checkpoint_path, check_same_thread=False
            )
            self._checkpointer = SqliteSaver(self._conn)
        return self._checkpointer

    def thread_config(self) -> dict:
        """Return the LangGraph config selecting this student's thread."""
        return {"configurable": {"thread_id": self.thread_id}}

    def close(self) -> None:
        """Close the sqlite connection; the checkpoint file remains on disk."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._checkpointer = None

    def load_training_state(self) -> dict:
        """Load training-state.json or return a fresh state (task 4.2)."""
        return TrainingStateStore(path=self.training_state_path).load()

    def save_training_state(self, state: dict) -> None:
        """Persist training-state.json (task 4.2)."""
        TrainingStateStore(path=self.training_state_path).save(state)
