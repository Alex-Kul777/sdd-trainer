"""Unit tests for the MCP server layer (ADR-010, issue #9, tasks 1.1-1.2).

The seam is the same as in the graph unit tests (design.md): a real FastMCP
server whose ``LLMManager`` is wired to a fake OpenAI client — no network.
The SDK's in-memory transport (``create_connected_server_and_client_session``)
carries the actual MCP protocol, so every tool call exercises the full
path: FastMCP tool dispatch → step engine → compiled graph → checkpointer
→ payload. The stdio transport (``python -m sdd_trainer.mcp``) is proven by
the integration test (live GigaChat) and the demo script — any stray stdout
print in the server would corrupt the protocol stream and fail there.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import anyio
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from mcp.shared.memory import create_connected_server_and_client_session

from sdd_trainer.config import GigaChatConfig
from sdd_trainer.core.llm_manager import LLMManager
from sdd_trainer.core.memory import TrainingStateStore
from sdd_trainer.mcp import create_server

pytestmark = pytest.mark.unit

SERVER_NAME = "sdd-trainer"


# --- fake OpenAI client (the same seam as test_graph, no network) ---

def _tool_call_response(tool_name: str, arguments: str) -> SimpleNamespace:
    """Build an openai-like completion whose message carries one tool call."""
    function = SimpleNamespace(name=tool_name, arguments=arguments)
    tool_call = SimpleNamespace(id="call_1", type="function", function=function)
    message = SimpleNamespace(content=None, tool_calls=[tool_call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _text_response(text: str) -> SimpleNamespace:
    """Build an openai-like plain-text completion (for ``LLMManager.complete``)."""
    message = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeOpenAI:
    """Stand-in for ``openai.OpenAI`` recording ``create()`` calls (test seam)."""

    def __init__(self, replies: list) -> None:
        self._replies = list(replies)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model: str, messages: list[dict], **kwargs) -> SimpleNamespace:
        self.calls.append({"model": model, "messages": messages, **kwargs})
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, str):
            return _text_response(reply)
        return reply


def _assessment_payload(
    level: str = "partial",
    confidence: float = 0.8,
    justification: str = "Знает про specs/, но путается в change proposals.",
) -> str:
    return json.dumps(
        {
            "domain": "openspec-basics",
            "level": level,
            "justification": justification,
            "confidence": confidence,
        },
        ensure_ascii=False,
    )


def _route_payload(path: str = "partial", reason: str = "Есть пробелы.") -> str:
    return json.dumps({"path": path, "reason": reason}, ensure_ascii=False)


def _docs_payload(
    needs_docs: bool = False,
    query: str = "",
    reason: str = "Скелета достаточно для полного урока.",
) -> str:
    return json.dumps(
        {"needs_docs": needs_docs, "query": query, "reason": reason},
        ensure_ascii=False,
    )


LESSON_TEXT = "# OpenSpec-основы — урок\n\n## Goal\nПонять specs/ и changes/.\n"


def _confident_replies(
    level: str = "partial", confidence: float = 0.9
) -> list:
    """Fake replies for a confident session: assessment → route → docs → lesson."""
    return [
        _tool_call_response(
            "Assessment", _assessment_payload(level=level, confidence=confidence)
        ),
        _tool_call_response("RouteDecision", _route_payload(path=level)),
        _tool_call_response("DocsDecision", _docs_payload()),
        LESSON_TEXT,
    ]


def _server(replies: list, checkpointer=None):
    """Build the MCP server over a fake LLM (no network, in-memory checkpoint).

    The training-state store points at a throwaway temp file: unit tests
    must never touch the repo's runtime ``data/training-state.json``.
    """
    import tempfile
    from pathlib import Path

    llm = LLMManager(config=GigaChatConfig(api_key="test"), client=FakeOpenAI(replies))
    state_store = TrainingStateStore(
        path=Path(tempfile.mkdtemp()) / "training-state.json"
    )
    return create_server(
        llm,
        checkpointer=checkpointer or InMemorySaver(),
        state_store=state_store,
    )


def _call_tools(server, tool_calls: list[tuple[str, dict]]) -> list[dict]:
    """Drive the server through a real SDK client session; return payloads.

    ``tool_calls`` is a list of ``(tool_name, arguments)`` pairs executed in
    order against one in-memory MCP connection. Each result's first content
    block is parsed from the FastMCP JSON serialization into a dict.
    """
    from mcp.types import CallToolResult

    async def scenario() -> list[CallToolResult]:
        async with create_connected_server_and_client_session(server) as session:
            await session.initialize()
            results = []
            for name, arguments in tool_calls:
                results.append(await session.call_tool(name, arguments))
            return results

    results = anyio.run(scenario)
    payloads = []
    for result in results:
        assert not result.isError, f"tool call failed: {result.content}"
        payloads.append(json.loads(result.content[0].text))
    return payloads


# --- 1.1: minimal carcass — a valid MCP server behind the SDK client ---

def test_server_handshake_over_in_memory_transport():
    """The factory returns a FastMCP server a real SDK client can talk to.

    Tracer-bullet minimum (task 1.1): ``create_server`` assembles a valid
    MCP server (initialize handshake succeeds, server name per ADR-010)
    over the LLM seam — the same FakeOpenAI wiring as the graph tests.
    """
    server = _server(_confident_replies())
    from mcp.server.fastmcp import FastMCP

    assert isinstance(server, FastMCP)

    async def scenario():
        async with create_connected_server_and_client_session(server) as session:
            return await session.initialize()

    init = anyio.run(scenario)
    assert init.serverInfo.name == SERVER_NAME


# --- 1.2: session tools — one call = one graph step (ADR-010) ---

def test_start_session_asks_calibration_question():
    """start_session on a fresh thread returns the calibration question.

    One call = one graph step (ADR-010): the graph runs from START up to
    the assess node's interrupt and the tool returns that interrupt's
    payload — the calibration question under the student's thread id
    (ADR-008), with no verdict yet (the LLM is called only after the
    answer — the fake client must stay untouched).
    """
    from sdd_trainer.core.prompts import CALIBRATION_QUESTION

    server = _server(_confident_replies())
    (payload,) = _call_tools(server, [("start_session", {"student": "unit_mcp"})])

    assert payload["type"] == "question"
    assert payload["question_kind"] == "calibration"
    assert payload["question"] == CALIBRATION_QUESTION
    assert payload["student"] == "unit_mcp"
    assert payload["thread_id"] == "student:unit_mcp"
    assert payload["resumed"] is False
    assert payload["done"] is False
    assert payload["assessment"] is None
    assert payload["route"] is None


def test_answer_calibration_returns_verdict_and_route():
    """answer_calibration resumes the graph and returns verdict + route.

    One call = one step (ADR-010): the answer resumes the assess node, the
    graph runs assess → route → teach → quiz and stops at the first quiz
    question. The payload carries the assessment verdict, the selected
    route and the pending question — quiz answering itself arrives in M2
    (issue #10), so for M1 the assess session ends at this verdict.
    """
    server = _server(_confident_replies(level="partial", confidence=0.9))
    payloads = _call_tools(
        server,
        [
            ("start_session", {"student": "unit_mcp"}),
            (
                "answer_calibration",
                {
                    "student": "unit_mcp",
                    "answer": "specs/ — стабильные спеки, changes/ — предложения изменений",
                },
            ),
        ],
    )

    verdict = payloads[1]
    assert verdict["type"] == "question"
    assert verdict["question_kind"] == "quiz"
    assert verdict["question"]  # the first quiz question is pending
    assert verdict["assessment"]["level"] == "partial"
    assert verdict["assessment"]["confidence"] == 0.9
    assert verdict["route"]["path"] == "partial"
    assert verdict["done"] is False
    # the session log carries the verdict and route entries (course criteria)
    assert any("Оценка: partial" in entry for entry in verdict["log"])
    assert any("Маршрут: partial" in entry for entry in verdict["log"])


def test_low_confidence_clarification_loop():
    """Low confidence routes to clarification; answer_clarification re-assesses.

    The deterministic clarification path (confidence below the threshold,
    course criterion 5): answer_calibration returns a clarification
    question instead of a verdict; answer_clarification feeds the
    follow-up answer back, the re-assessment is confident and the route
    is selected — the payload carries the re-assessed verdict + route.
    """
    replies = [
        _tool_call_response(
            "Assessment", _assessment_payload(confidence=0.3)
        ),
        _tool_call_response(
            "Assessment",
            _assessment_payload(level="partial", confidence=0.85),
        ),
        _tool_call_response("RouteDecision", _route_payload(path="partial")),
        _tool_call_response("DocsDecision", _docs_payload()),
        LESSON_TEXT,
    ]
    server = _server(replies)
    payloads = _call_tools(
        server,
        [
            ("start_session", {"student": "unit_mcp"}),
            (
                "answer_calibration",
                {"student": "unit_mcp", "answer": "что-то слышал про спеки"},
            ),
            (
                "answer_clarification",
                {
                    "student": "unit_mcp",
                    "answer": "specs/ видел в репозитории, changes/ не трогал",
                },
            ),
        ],
    )

    clarification = payloads[1]
    assert clarification["type"] == "question"
    assert clarification["question_kind"] == "clarification"
    assert clarification["question"]  # the follow-up question itself
    assert clarification["route"]["path"] == "clarification"
    assert clarification["assessment"]["confidence"] == 0.3

    verdict = payloads[2]
    assert verdict["question_kind"] == "quiz"
    assert verdict["assessment"]["level"] == "partial"
    assert verdict["assessment"]["confidence"] == 0.85
    assert verdict["route"]["path"] == "partial"
    assert any("Переоценка: partial" in entry for entry in verdict["log"])
