"""Unit tests for configuration (ADR-005 / ADR-008 values, no network)."""
from __future__ import annotations

import pytest

from sdd_trainer.config import GigaChatConfig, TrainerConfig

pytestmark = pytest.mark.unit


class TestGigaChatConfig:
    """ADR-005: GigaChat via the OpenAI-compatible cloud.ru API."""

    def test_base_url(self) -> None:
        cfg = GigaChatConfig()
        assert cfg.base_url == "https://foundation-models.api.cloud.ru/v1"

    def test_primary_model(self) -> None:
        assert GigaChatConfig().model == "GigaChat/GigaChat-3-Pro"

    def test_fallback_model(self) -> None:
        assert GigaChatConfig().fallback_model == "GigaChat/GigaChat-3.5-Reasoning"

    def test_is_configured(self) -> None:
        assert GigaChatConfig(api_key="").is_configured() is False
        assert GigaChatConfig(api_key="test-key").is_configured() is True


class TestTrainerConfig:
    """ADR-008: SqliteSaver persistence and the student thread id."""

    def test_thread_id(self) -> None:
        assert TrainerConfig().thread_id == "student:alex"

    def test_paths(self) -> None:
        cfg = TrainerConfig()
        assert cfg.training_state_path.name == "training-state.json"
        assert cfg.checkpoint_path.name == "checkpoints.sqlite"
