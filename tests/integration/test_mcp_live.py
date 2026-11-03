"""Integration tests: the MCP server over stdio with real GigaChat (issues #9-#10).

The full tracer bullet: the SDK MCP client spawns the real server subprocess
(``python -m sdd_trainer.mcp``) over stdio and drives sessions end-to-end —
any stray stdout print in the server would corrupt the protocol stream and
fail here, so these tests double as the stdout-vs-protocol canary. Skipped
unless ``GIGACHAT_KEY`` is set (the server entry point demands it). The
server runs with its real configuration (SqliteSaver at
``data/checkpoints.sqlite`` — a git-ignored runtime artifact, exactly what
a console session writes); each run uses a fresh student thread so a
previous run's pending question can never collide with this one.

M2 (issue #10): the full session reaches the F1 quiz verdict (task 2.1)
and the recorded progress (task 2.3); the direct tools run over the real
server too (task 2.2) — analyze_repo is a local scan, search_docs hits
live Tavily (needs ``TAVILY_API_KEY``; the geo-block note applies — run
with ``HTTPS_PROXY=http://127.0.0.1:7890``, the mihomo split tunnel).
"""
from __future__ import annotations

import json
import os
import sys
import time

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.integration

requires_key = pytest.mark.skipif(
    not os.getenv("GIGACHAT_KEY"),
    reason="GIGACHAT_KEY not set — live GigaChat tests skipped (see .env.example)",
)

requires_tavily = pytest.mark.skipif(
    not os.getenv("TAVILY_API_KEY"),
    reason="TAVILY_API_KEY not set — live Tavily tests skipped (see .env.example)",
)

KNOWLEDGEABLE_ANSWER = (
    "OpenSpec — инструмент spec-driven development. В specs/ лежат стабильные "
    "спецификации требований (source of truth), в changes/ — change proposals: "
    "предложения изменений с proposal.md, design.md, tasks.md и дельтой спеки. "
    "Proposal проходит review, применяется и архивируется, а спецификация "
    "остаётся источником истины."
)

#: Follow-up answer for the clarification loop — a live model may route a
#: low-confidence assessment there (bounded by the graph's round limit).
CLARIFICATION_ANSWER = (
    "Знаком со структурой specs/ и changes/, писал tasks.md для proposal, "
    "но с дельтами спецификаций почти не работал."
)

#: The M1 session-tool contract a real client must see (issue #9).
M1_TOOLS = {"start_session", "answer_calibration", "answer_clarification"}

#: The M2 tool set a real client must see (issue #10).
M2_TOOLS = {"answer_quiz_question", "analyze_repo", "search_docs", "get_progress"}


def _quiz_reference_answers(domain: str = "openspec-basics") -> list[str]:
    """Reference answers from the authored quiz (deterministic F1 = 1).

    The live quiz scoring is the deterministic token F1 (ADR-009) — the
    reference answers pass regardless of the live model's behavior, so
    the full-session test asserts a stable verdict.
    """
    from sdd_trainer.lessons import load_quiz

    return [q.reference_answer for q in load_quiz(domain).questions]


def _server_params() -> StdioServerParameters:
    """Spawn the real server: the venv python running the package entry point.

    Only trainer-related environment travels to the child (the server also
    loads ``.env`` itself); key values are never printed.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key.startswith(("GIGACHAT_", "TAVILY_", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"))
    }
    return StdioServerParameters(
        command=sys.executable, args=["-m", "sdd_trainer.mcp"], env=env
    )


def _payload(result) -> dict:
    """Parse a tool result into the payload dict (fail loudly on MCP errors)."""
    assert not result.isError, f"tool call failed: {result.content}"
    return json.loads(result.content[0].text)


@requires_key
def test_assess_session_end_to_end_over_stdio():
    """A real MCP client drives the assess session to a verdict + route.

    start_session → calibration question; answer_calibration → verdict +
    route (following the clarification loop if the live model asks for it);
    the session stops at the first quiz question — quiz answering is M2
    (issue #10), for M1 the assess session ends at the verdict.
    """
    student = f"mcp_live_{int(time.time())}"

    async def scenario() -> dict:
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                assert M1_TOOLS <= {tool.name for tool in tools.tools}

                start = _payload(
                    await session.call_tool(
                        "start_session", {"student": student}
                    )
                )
                assert start["type"] == "question"
                assert start["question_kind"] == "calibration"
                assert start["question"]
                assert start["thread_id"] == f"student:{student}"

                payload = _payload(
                    await session.call_tool(
                        "answer_calibration",
                        {"student": student, "answer": KNOWLEDGEABLE_ANSWER},
                    )
                )
                for _ in range(3):  # bounded: the graph allows max 2 rounds
                    if payload["type"] == "error":
                        raise AssertionError(payload["message"])
                    if payload.get("question_kind") != "clarification":
                        break
                    payload = _payload(
                        await session.call_tool(
                            "answer_clarification",
                            {
                                "student": student,
                                "answer": CLARIFICATION_ANSWER,
                            },
                        )
                    )
                return payload

    verdict = anyio.run(scenario)

    assert verdict["type"] == "question"
    assert verdict["assessment"], f"no verdict delivered: {verdict}"
    assert verdict["assessment"]["level"] in {"new_topic", "partial", "knows_it"}
    assert 0.0 <= verdict["assessment"]["confidence"] <= 1.0
    assert verdict["route"]["path"] in {"knows_it", "partial", "new_topic"}
    assert verdict["route"]["reason"]
    # the assess session ends at the first quiz question (M2 picks it up)
    assert verdict["question_kind"] in {"quiz", None}
    assert verdict["done"] is False


# --- M2 (issue #10): full session, direct tools, progress ---


@requires_key
def test_full_session_to_quiz_verdict_over_stdio():
    """A real MCP client drives the full session to the F1 quiz verdict.

    The M2 tracer bullet (task 2.1): calibration → (clarifications) →
    verdict/route → lesson → quiz one question per call → the weighted
    F1 verdict (threshold 0.60, ADR-009) → the recorded progress
    (task 2.3). Quiz scoring is deterministic, so reference answers pass
    regardless of the live model's assessment behavior.
    """
    student = f"mcp_live_{int(time.time())}"

    async def scenario() -> tuple[dict, dict, dict]:
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                assert M1_TOOLS | M2_TOOLS <= {tool.name for tool in tools.tools}

                # the runtime training-state accumulates across runs
                # (console smokes, demos) — assert deltas from this baseline
                baseline = _payload(
                    await session.call_tool(
                        "get_progress", {"student": student}
                    )
                )
                base_entry = (baseline.get("domains") or {}).get(
                    "openspec-basics"
                ) or {}

                start = _payload(
                    await session.call_tool(
                        "start_session", {"student": student}
                    )
                )
                assert start["type"] == "question"
                assert start["question_kind"] == "calibration"

                payload = _payload(
                    await session.call_tool(
                        "answer_calibration",
                        {"student": student, "answer": KNOWLEDGEABLE_ANSWER},
                    )
                )
                for _ in range(3):  # bounded: the graph allows max 2 rounds
                    if payload["type"] == "error":
                        raise AssertionError(payload["message"])
                    if payload.get("question_kind") != "clarification":
                        break
                    payload = _payload(
                        await session.call_tool(
                            "answer_clarification",
                            {
                                "student": student,
                                "answer": CLARIFICATION_ANSWER,
                            },
                        )
                    )

                assert payload.get("question_kind") == "quiz", (
                    f"the session did not reach the quiz: {payload}"
                )
                # the lesson is present when the route teaches first
                # (partial/new_topic); a knows_it route goes straight to
                # the quiz — the graph skips teach for students who know it
                route_path = (payload.get("route") or {}).get("path")
                if route_path in {"partial", "new_topic"}:
                    assert payload.get("lesson"), "no lesson in the payload"

                for answer in _quiz_reference_answers():
                    payload = _payload(
                        await session.call_tool(
                            "answer_quiz_question",
                            {"student": student, "answer": answer},
                        )
                    )
                    if payload["type"] == "error":
                        raise AssertionError(payload["message"])

                progress = _payload(
                    await session.call_tool(
                        "get_progress", {"student": student}
                    )
                )
                return payload, progress, base_entry

    verdict, progress, base_entry = anyio.run(scenario)

    assert verdict["type"] == "result"
    assert verdict["done"] is True
    assert verdict["quiz"]["domain"] == "openspec-basics"
    assert verdict["quiz"]["passed"] is True
    assert verdict["quiz"]["score"] >= 0.60
    assert verdict["assessment"]["level"] in {"new_topic", "partial", "knows_it"}
    # the recorded progress matches the verdict (task 2.3, ADR-008):
    # the score reflects this quiz, the streak and the completed count
    # grew by exactly this one passed quiz regardless of prior history
    entry = progress["domains"]["openspec-basics"]
    assert entry["score"] == verdict["quiz"]["score"]
    assert entry["streak"] == base_entry.get("streak", 0) + 1
    assert entry["completed_lessons"] == (
        base_entry.get("completed_lessons", 0) + 1
    )


@requires_key
def test_analyze_repo_over_stdio(tmp_path):
    """analyze_repo over the real server: a local scan, no LLM involved.

    The server boots with its real configuration (the entry point demands
    GIGACHAT_KEY), but the scan itself is a local filesystem pass — the
    same evidence the assess node weighs (task 2.2). A fixture repo with
    hand-counted expectations: 1 domain, 1 SHALL, 1 scenario.
    """
    repo = tmp_path / "student-repo"
    spec = repo / "openspec" / "specs" / "console-trainer"
    spec.mkdir(parents=True)
    (spec / "spec.md").write_text(
        "# console-trainer\n\n"
        "### Requirement: Session\nThe trainer SHALL run a session.\n\n"
        "#### Scenario: Full session\n"
        "- **WHEN** the student starts\n"
        "- **THEN** the trainer assesses\n",
        encoding="utf-8",
    )

    async def scenario() -> dict:
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return _payload(
                    await session.call_tool(
                        "analyze_repo", {"path": str(repo)}
                    )
                )

    payload = anyio.run(scenario)
    assert payload["type"] == "repo_analysis"
    assert payload["analysis"]["has_openspec"] is True
    assert payload["analysis"]["spec_domains"] == ["console-trainer"]
    assert payload["analysis"]["shall_count"] == 1
    assert payload["analysis"]["scenario_count"] == 1


@requires_key
@requires_tavily
def test_search_docs_live_over_stdio():
    """search_docs over the real server hits live Tavily (ADR-006, task 2.2).

    Needs both keys: the server entry point demands GIGACHAT_KEY, the
    search itself demands TAVILY_API_KEY. The geo-block note applies:
    run with ``HTTPS_PROXY=http://127.0.0.1:7890`` (mihomo split tunnel)
    — the env passthrough forwards the proxy variables to the server.
    """

    async def scenario() -> dict:
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return _payload(
                    await session.call_tool(
                        "search_docs",
                        {"query": "OpenSpec spec-driven development workflow"},
                    )
                )

    payload = anyio.run(scenario)
    assert payload["type"] == "docs_results"
    assert payload["results"], "ожидали хотя бы один результат живого поиска"
    for result in payload["results"]:
        assert set(result) == {"title", "url", "content"}
        assert result["url"].startswith("http")
