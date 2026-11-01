"""Persistence for the trainer (criterion 4, AIA_04, ADR-008).

Two layers:

- LangGraph checkpointer — ``SqliteSaver`` at ``data/checkpoints.sqlite``
  with ``thread_id="student:alex"`` (InMemorySaver in unit tests only);
- training state — ``data/training-state.json``: per-domain progress
  (score, streak) across the 6 SDD domains (openclaw-tutor pattern).

Phase 0: stubs only. Implemented by the ``add-console-trainer`` change
(phase 1).
"""
from __future__ import annotations


class MemoryManager:
    """Checkpointer + training-state persistence (implemented in phase 1)."""

    def __init__(self, thread_id: str = "student:alex") -> None:
        """Store the student thread id (ADR-008)."""
        self.thread_id = thread_id

    def get_checkpointer(self):
        """Return a SqliteSaver checkpointer (implemented in phase 1)."""
        pass

    def load_training_state(self) -> dict:
        """Load training-state.json or return a fresh state (phase 1)."""
        pass

    def save_training_state(self, state: dict) -> None:
        """Persist training-state.json (implemented in phase 1)."""
        pass
