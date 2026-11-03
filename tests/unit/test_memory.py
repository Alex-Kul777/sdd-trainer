"""Unit tests for the persistence layer (criterion 4, ADR-008, task 4.1)."""
from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from sdd_trainer.config import trainer_config
from sdd_trainer.core.memory import MemoryManager, TrainingStateStore

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


class TestTrainingStateStore:
    """TrainingStateStore: file-backed training-state.json (task 4.2, T5)."""

    def test_fresh_state_when_file_missing(self, tmp_path: Path) -> None:
        store = TrainingStateStore(path=tmp_path / "training-state.json")

        assert store.load() == {"domains": {}}

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        store = TrainingStateStore(path=tmp_path / "training-state.json")
        state = {
            "domains": {
                "openspec-basics": {
                    "score": 0.84,
                    "streak": 2,
                    "completed_lessons": 2,
                }
            }
        }

        store.save(state)

        assert store.load() == state

    def test_state_survives_restart_via_new_instance(self, tmp_path: Path) -> None:
        path = tmp_path / "training-state.json"
        TrainingStateStore(path=path).save(
            {"domains": {"openspec-basics": {"score": 1.0, "streak": 1, "completed_lessons": 1}}}
        )

        restarted = TrainingStateStore(path=path)

        assert restarted.load()["domains"]["openspec-basics"]["streak"] == 1

    def test_passed_quiz_starts_streak_and_completes_lesson(
        self, tmp_path: Path
    ) -> None:
        store = TrainingStateStore(path=tmp_path / "training-state.json")

        entry = store.record_quiz_result("openspec-basics", score=0.84, passed=True)

        assert entry == {"score": 0.84, "streak": 1, "completed_lessons": 1}
        assert store.load()["domains"]["openspec-basics"] == entry

    def test_consecutive_passed_quizzes_grow_the_streak(
        self, tmp_path: Path
    ) -> None:
        store = TrainingStateStore(path=tmp_path / "training-state.json")
        store.record_quiz_result("openspec-basics", score=0.8, passed=True)

        entry = store.record_quiz_result("openspec-basics", score=0.9, passed=True)

        assert entry["streak"] == 2
        assert entry["score"] == 0.9  # latest score, not the best
        assert entry["completed_lessons"] == 2

    def test_failed_quiz_resets_streak_and_keeps_completed_count(
        self, tmp_path: Path
    ) -> None:
        store = TrainingStateStore(path=tmp_path / "training-state.json")
        store.record_quiz_result("openspec-basics", score=0.9, passed=True)

        entry = store.record_quiz_result("openspec-basics", score=0.2, passed=False)

        assert entry == {"score": 0.2, "streak": 0, "completed_lessons": 1}

    def test_domains_are_tracked_independently(self, tmp_path: Path) -> None:
        store = TrainingStateStore(path=tmp_path / "training-state.json")
        store.record_quiz_result("openspec-basics", score=0.9, passed=True)

        entry = store.record_quiz_result("requirement-writing", score=0.5, passed=False)

        assert entry["streak"] == 0
        domains = store.load()["domains"]
        assert domains["openspec-basics"]["streak"] == 1
        assert domains["requirement-writing"]["streak"] == 0

    def test_corrupt_state_file_fails_loudly(self, tmp_path: Path) -> None:
        path = tmp_path / "training-state.json"
        path.write_text("{not json", encoding="utf-8")
        store = TrainingStateStore(path=path)

        with pytest.raises(ValueError):
            store.load()


class TestMemoryManagerTrainingState:
    """MemoryManager delegates training state to the store (task 4.2)."""

    def test_default_training_state_path_matches_adr008(self) -> None:
        manager = MemoryManager(thread_id="student:test")

        assert manager.training_state_path == trainer_config.training_state_path

    def test_load_reads_the_state_file(self, tmp_path: Path) -> None:
        path = tmp_path / "training-state.json"
        TrainingStateStore(path=path).save(
            {"domains": {"openspec-basics": {"score": 1.0, "streak": 1, "completed_lessons": 1}}}
        )
        manager = MemoryManager(
            thread_id="student:test",
            checkpoint_path=tmp_path / "checkpoints.sqlite",
            training_state_path=path,
        )

        assert manager.load_training_state()["domains"]["openspec-basics"]["streak"] == 1

    def test_save_writes_the_state_file(self, tmp_path: Path) -> None:
        path = tmp_path / "training-state.json"
        manager = MemoryManager(
            thread_id="student:test",
            checkpoint_path=tmp_path / "checkpoints.sqlite",
            training_state_path=path,
        )

        manager.save_training_state({"domains": {}})

        assert TrainingStateStore(path=path).load() == {"domains": {}}
