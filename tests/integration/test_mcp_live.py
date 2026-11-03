"""Integration tests: the MCP server over stdio with real GigaChat (issue #9, task 1.3).

The full tracer bullet: the SDK MCP client spawns the real server subprocess
(``python -m sdd_trainer.mcp``) over stdio and drives an assess session
end-to-end — any stray stdout print in the server would corrupt the protocol
stream and fail here, so this test doubles as the stdout-vs-protocol canary.
Skipped unless ``GIGACHAT_KEY`` is set. The server runs with its real
configuration (SqliteSaver at ``data/checkpoints.sqlite`` — a git-ignored
runtime artifact, exactly what a console session writes); each run uses a
fresh student thread so a previous run's pending quiz question (M2
territory, issue #10) can never collide with this one.
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


def _server_params() -> StdioServerParameters:
    """Spawn the real server: the venv python running the package entry point.

    Only trainer-related environment travels to the child (the server also
    loads ``.env`` itself); key values are never printed.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key.startswith(("GIGACHAT_", "TAVILY_"))
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
