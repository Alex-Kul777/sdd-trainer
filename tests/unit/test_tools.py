"""Unit tests for search_sdd_docs — the Tavily tool (ADR-006, task 2.3).

No network: the httpx client is the test seam (the same pattern as
FakeOpenAI in test_llm_manager — an external collaborator faked at the
boundary, never an internal one mocked). Expected outputs are literals /
worked examples written here, independent of the implementation.
"""
from __future__ import annotations

import httpx
import pytest

from sdd_trainer.config import TavilyConfig
from sdd_trainer.core import tools as tools_module
from sdd_trainer.core.tools import search_sdd_docs

pytestmark = pytest.mark.unit

#: A canned Tavily /search response (worked example, shape per Tavily API).
TAVILY_PAYLOAD = {
    "query": "OpenSpec workflow",
    "results": [
        {
            "title": "OpenSpec — workflow",
            "url": "https://example.org/openspec-workflow",
            "content": "explore → propose → apply → archive",
            "score": 0.97,
        },
        {
            "title": "Spec-Driven Development",
            "url": "https://example.org/sdd",
            "content": "спецификация — источник истины",
            "score": 0.91,
        },
    ],
}

#: What the tool must return for TAVILY_PAYLOAD: title / url / content only.
EXPECTED_RESULTS = [
    {
        "title": "OpenSpec — workflow",
        "url": "https://example.org/openspec-workflow",
        "content": "explore → propose → apply → archive",
    },
    {
        "title": "Spec-Driven Development",
        "url": "https://example.org/sdd",
        "content": "спецификация — источник истины",
    },
]

_CONFIG = TavilyConfig(api_key="test-tavily-key")


class FakeResponse:
    """Stand-in for ``httpx.Response``."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeHttpx:
    """Stand-in for ``httpx.Client`` recording ``post()`` calls (test seam)."""

    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self._payload = payload
        self._error = error
        self.requests: list[dict] = []
        self.closed = False

    def post(self, url: str, *, json=None, headers=None, timeout=None):
        self.requests.append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        if self._error is not None:
            raise self._error
        return FakeResponse(self._payload)

    def close(self) -> None:
        self.closed = True

    # httpx.Client is normally used as a context manager — the fake
    # supports the same protocol (the fake must behave like the real
    # collaborator, not a stripped-down version of it).
    def __enter__(self) -> "FakeHttpx":
        return self

    def __exit__(self, *exc_info) -> bool:
        self.close()
        return False


class TestSearchSddDocs:
    """search_sdd_docs: fresh SDD/OpenSpec docs via Tavily (ADR-006)."""

    def test_returns_title_url_content_per_result(self) -> None:
        fake = FakeHttpx(TAVILY_PAYLOAD)

        results = search_sdd_docs("OpenSpec workflow", config=_CONFIG, client=fake)

        assert results == EXPECTED_RESULTS

    def test_empty_results_come_back_as_empty_list(self) -> None:
        fake = FakeHttpx({"query": "ничего", "results": []})

        assert search_sdd_docs("ничего", config=_CONFIG, client=fake) == []

    def test_posts_bearer_query_and_max_results_to_search_endpoint(self) -> None:
        fake = FakeHttpx(TAVILY_PAYLOAD)

        search_sdd_docs("OpenSpec workflow", config=_CONFIG, client=fake)

        (request,) = fake.requests
        assert request["url"] == "https://api.tavily.com/search"
        assert request["headers"] == {"Authorization": "Bearer test-tavily-key"}
        assert request["json"] == {"query": "OpenSpec workflow", "max_results": 5}
        assert request["timeout"] == 30

    def test_missing_api_key_raises_before_any_request(self) -> None:
        fake = FakeHttpx(TAVILY_PAYLOAD)

        with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
            search_sdd_docs(
                "OpenSpec workflow", config=TavilyConfig(api_key=""), client=fake
            )

        assert fake.requests == []

    def test_transport_errors_propagate(self) -> None:
        error = httpx.ConnectError(
            "connection refused",
            request=httpx.Request("POST", "https://api.tavily.com/search"),
        )
        fake = FakeHttpx(error=error)

        with pytest.raises(httpx.ConnectError):
            search_sdd_docs("OpenSpec workflow", config=_CONFIG, client=fake)

    def test_injected_client_is_caller_owned_and_not_closed(self) -> None:
        fake = FakeHttpx(TAVILY_PAYLOAD)

        search_sdd_docs("OpenSpec workflow", config=_CONFIG, client=fake)

        assert fake.closed is False

    def test_own_client_is_created_and_closed(self, monkeypatch) -> None:
        fake = FakeHttpx(TAVILY_PAYLOAD)
        monkeypatch.setattr(
            tools_module.httpx, "Client", lambda timeout=None: fake
        )

        search_sdd_docs("OpenSpec workflow", config=_CONFIG)

        assert fake.closed is True
        assert len(fake.requests) == 1
