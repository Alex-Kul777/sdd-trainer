"""Unit tests for the persistence layer (criterion 4, ADR-008, task 4.1)."""
from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from sdd_trainer.config import trainer_config
from sdd_trainer.core.memory import MemoryManager

pytestmark = pytest.mark.unit


class TestCheckpointer:
    """get_checkpointer(): lazy SqliteSaver at the ADR-008 path."""

    def test_creates_sqlite_file_with_missing_parent_dir(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "data" / "checkpoints.sqlite"
        manager = MemoryManager(thread_id="student:test", checkpoint_path=path)

        checkpointer = manager.get_checkpointer()

        assert isinstance(checkpointer, SqliteSaver)
        assert path.exists()

    def test_same_instance_returned_until_close(self, tmp_path: Path) -> None:
        manager = MemoryManager(
            thread_id="student:test",
            checkpoint_path=tmp_path / "checkpoints.sqlite",
        )

        first = manager.get_checkpointer()
        assert manager.get_checkpointer() is first

        manager.close()
        second = manager.get_checkpointer()  # reopens the same file
        assert second is not first
        manager.close()

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        manager = MemoryManager(
            thread_id="student:test",
            checkpoint_path=tmp_path / "checkpoints.sqlite",
        )
        manager.get_checkpointer()

        manager.close()
        manager.close()  # no error

    def test_checkpoint_file_survives_close(self, tmp_path: Path) -> None:
        path = tmp_path / "checkpoints.sqlite"
        manager = MemoryManager(thread_id="student:test", checkpoint_path=path)
        manager.get_checkpointer()
        manager.close()

        assert path.exists()  # the point of criterion 4


class TestThreadConvention:
    """thread_id / thread_config follow the ADR-008 convention."""

    def test_default_thread_id_is_student_alex(self) -> None:
        assert MemoryManager().thread_id == "student:alex"

    def test_default_checkpoint_path_matches_adr008(self) -> None:
        manager = MemoryManager()
        assert manager.checkpoint_path == trainer_config.checkpoint_path
        assert manager.checkpoint_path.name == "checkpoints.sqlite"
        assert manager.checkpoint_path.parent.name == "data"

    def test_thread_config_shape(self) -> None:
        manager = MemoryManager(thread_id="student:maria")

        assert manager.thread_config() == {
            "configurable": {"thread_id": "student:maria"}
        }


class TestTrainingStateStubs:
    """training-state.json is task 4.2 — ticket T5 (issue #6): stubs stay."""

    def test_load_returns_empty_state_for_now(self) -> None:
        manager = MemoryManager(thread_id="student:test")

        assert manager.load_training_state() == {}

    def test_save_is_a_no_op_for_now(self, tmp_path: Path) -> None:
        manager = MemoryManager(
            thread_id="student:test",
            checkpoint_path=tmp_path / "checkpoints.sqlite",
        )

        manager.save_training_state({"domain": "openspec-basics"})  # no error
