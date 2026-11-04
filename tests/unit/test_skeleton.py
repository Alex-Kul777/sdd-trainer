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


def test_single_lesson_domain() -> None:
    """The curriculum lists exactly the domains with authored content.

    Roadmap domains (Phase 3 curriculum) live in ``docs/roadmap.md``,
    not in the code constant — LESSON_DOMAINS reflects reality.
    """
    from sdd_trainer.lessons import LESSON_DOMAINS

    assert len(LESSON_DOMAINS) == 1
    assert "openspec-basics" in LESSON_DOMAINS
