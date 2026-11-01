"""Import smoke test: every skeleton module imports cleanly (phase 0)."""
from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit

MODULES = [
    "sdd_trainer",
    "sdd_trainer.config",
    "sdd_trainer.models",
    "sdd_trainer.token_counter",
    "sdd_trainer.logging_utils",
    "sdd_trainer.core",
    "sdd_trainer.core.llm_manager",
    "sdd_trainer.core.graph",
    "sdd_trainer.core.tools",
    "sdd_trainer.core.memory",
    "sdd_trainer.lessons",
    "sdd_trainer.console",
    "sdd_trainer.api",
    "sdd_trainer.mcp",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_module_imports_cleanly(module_name: str) -> None:
    """WHEN a skeleton module is imported THEN it imports without errors."""
    importlib.import_module(module_name)


def test_six_lesson_domains() -> None:
    """The curriculum covers exactly the 6 SDD domains."""
    from sdd_trainer.lessons import LESSON_DOMAINS

    assert len(LESSON_DOMAINS) == 6
    assert "requirement-writing" in LESSON_DOMAINS
