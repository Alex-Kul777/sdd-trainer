"""Unit tests for configuration (ADR-005 / ADR-008 values, no network)."""
from __future__ import annotations

import pytest

from sdd_trainer.config import GigaChatConfig, TavilyConfig, TrainerConfig

pytestmark = pytest.mark.unit


class TestGigaChatConfig:
    """ADR-005: GigaChat via the OpenAI-compatible cloud.ru API."""

    def test_base_url(self) -> None:
        cfg = GigaChatConfig()
        assert cfg.base_url == "https://foundation-models.api.cloud.ru/v1"

    def test_primary_model(self) -> None:
        assert GigaChatConfig().model == "GigaChat/GigaChat-3-Pro"

    def test_fallback_model(self) -> None:
        # Exact ID confirmed via live models.list (add-console-trainer task 1.1)
        assert GigaChatConfig().fallback_model == "ai-sage/GigaChat3.5-432B-A28B-Reasoning"

    def test_is_configured(self) -> None:
        assert GigaChatConfig(api_key="").is_configured() is False
        assert GigaChatConfig(api_key="test-key").is_configured() is True

    def test_api_key_comes_from_env_not_hardcoded(self, monkeypatch) -> None:
        """The key is read from GIGACHAT_KEY at instantiation — never hardcoded."""
        monkeypatch.delenv("GIGACHAT_KEY", raising=False)
        assert GigaChatConfig().api_key == ""
        monkeypatch.setenv("GIGACHAT_KEY", "env-provided-key")
        assert GigaChatConfig().api_key == "env-provided-key"


class TestTavilyConfig:
    """ADR-006: Tavily search with the existing TAVILY_API_KEY secret."""

    def test_base_url(self) -> None:
        assert TavilyConfig().base_url == "https://api.tavily.com"

    def test_max_results_default(self) -> None:
        assert TavilyConfig().max_results == 5

    def test_is_configured(self) -> None:
        assert TavilyConfig(api_key="").is_configured() is False
        assert TavilyConfig(api_key="tvly-test").is_configured() is True

    def test_api_key_comes_from_env_not_hardcoded(self, monkeypatch) -> None:
        """The key is read from TAVILY_API_KEY at instantiation (ADR-006)."""
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        assert TavilyConfig().api_key == ""
        monkeypatch.setenv("TAVILY_API_KEY", "env-tavily-key")
        assert TavilyConfig().api_key == "env-tavily-key"


class TestTrainerConfig:
    """ADR-008: SqliteSaver persistence and the student thread id."""

    def test_thread_id(self) -> None:
        assert TrainerConfig().thread_id == "student:alex"

    def test_paths(self) -> None:
        cfg = TrainerConfig()
        assert cfg.training_state_path.name == "training-state.json"
        assert cfg.checkpoint_path.name == "checkpoints.sqlite"
