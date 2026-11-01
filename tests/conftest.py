"""Shared pytest fixtures for SDD Trainer tests (rag_GigaChat convention)."""
from __future__ import annotations

from pathlib import Path

import pytest

from sdd_trainer.config import GigaChatConfig, TrainerConfig

PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def gigachat_config() -> GigaChatConfig:
    """GigaChat config with a dummy key — never touches the network."""
    return GigaChatConfig(api_key="test-key")


@pytest.fixture
def trainer_config(tmp_path: Path) -> TrainerConfig:
    """Trainer config pointing at a temporary data directory."""
    return TrainerConfig(
        data_dir=tmp_path / "data",
        prompts_dir=tmp_path / "prompts",
        training_state_path=tmp_path / "data" / "training-state.json",
        checkpoint_path=tmp_path / "data" / "checkpoints.sqlite",
    )
