"""Integration tests: search_sdd_docs against the real Tavily API (ADR-006).

Task 2.3 (issue #5). Skipped unless ``TAVILY_API_KEY`` is set (locally the
git-ignored ``.env`` provides it; CI without the secret skips). The seam is
the same as in the unit tests — ``search_sdd_docs`` — but wired to the real
endpoint (design.md).
"""
from __future__ import annotations

import os

import pytest

from sdd_trainer.config import TavilyConfig
from sdd_trainer.core.tools import search_sdd_docs

pytestmark = pytest.mark.integration

requires_tavily = pytest.mark.skipif(
    not os.getenv("TAVILY_API_KEY"),
    reason="TAVILY_API_KEY not set — live Tavily tests skipped (see .env.example)",
)


@requires_tavily
def test_search_sdd_docs_returns_real_results_live() -> None:
    """WHEN searching fresh OpenSpec docs THEN live Tavily returns title/url/content."""
    results = search_sdd_docs(
        "OpenSpec spec-driven development workflow", config=TavilyConfig()
    )

    assert isinstance(results, list)
    assert results, "ожидали хотя бы один результат живого поиска"
    for result in results:
        assert set(result) == {"title", "url", "content"}
        assert result["url"].startswith("http")
        assert result["title"].strip()
        assert result["content"].strip()
