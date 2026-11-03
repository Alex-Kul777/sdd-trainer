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


# --- state-machine guards and restart resilience (ADR-008) ---

def test_answer_tools_guard_the_state_machine():
    """Guards return error payloads naming the right tool — never a wrong resume.

    A session tool without a pending session, a mismatched question kind
    and an invalid student name each produce type "error" with guidance;
    the checkpoint is never fed an answer through the wrong interrupt.
    """
    server = _server(
        [_tool_call_response("Assessment", _assessment_payload(confidence=0.3))]
    )
    payloads = _call_tools(
        server,
        [
            # no session for this student yet
            ("answer_calibration", {"student": "ghost", "answer": "..."}),
            # invalid student name (thread id convention, ADR-008)
            ("start_session", {"student": "two words"}),
            # drive to a pending clarification, then call the wrong tool
            ("start_session", {"student": "unit_mcp"}),
            (
                "answer_calibration",
                {"student": "unit_mcp", "answer": "что-то слышал про спеки"},
            ),
            (
                "answer_calibration",
                {"student": "unit_mcp", "answer": "не тот инструмент"},
            ),
        ],
    )

    no_session = payloads[0]
    assert no_session["type"] == "error"
    assert "start_session" in no_session["message"]

    bad_name = payloads[1]
    assert bad_name["type"] == "error"
    assert "недопустимое имя" in bad_name["message"]

    assert payloads[3]["question_kind"] == "clarification"  # pending state
    mismatch = payloads[4]
    assert mismatch["type"] == "error"
    assert "answer_clarification" in mismatch["message"]


def _quiz_reference_answers(domain: str = "openspec-basics") -> list[str]:
    """Reference answers from the authored quiz data (deterministic F1 = 1).

    The real ``data/quizzes/<domain>.json`` — the same fixture the graph's
    quiz node loads — keeps the test honest: no reference answers are
    duplicated here, and the F1 scoring runs against the real references
    (ADR-009), exactly as in a live session.
    """
    from sdd_trainer.lessons import load_quiz

    return [q.reference_answer for q in load_quiz(domain).questions]


def test_start_session_resumes_pending_question_after_restart():
    """A new server instance over the same checkpointer resumes the session.

    The tools are stateless — the checkpoint IS the state (ADR-008/010):
    after a "restart" (a fresh create_server over the same saver) the same
    student gets the same pending calibration question with resumed=True.
    """
    from sdd_trainer.core.prompts import CALIBRATION_QUESTION

    checkpointer = InMemorySaver()
    first = _server(_confident_replies(), checkpointer=checkpointer)
    (payload,) = _call_tools(first, [("start_session", {"student": "unit_mcp"})])
    assert payload["resumed"] is False

    second = _server(_confident_replies(), checkpointer=checkpointer)
    (resumed,) = _call_tools(
        second, [("start_session", {"student": "unit_mcp"})]
    )
    assert resumed["type"] == "question"
    assert resumed["resumed"] is True
    assert resumed["question_kind"] == "calibration"
    assert resumed["question"] == CALIBRATION_QUESTION


# --- 2.1: quiz stepwise — answer_quiz_question (issue #10) ---

def test_answer_quiz_question_steps_to_f1_verdict():
    """The quiz is answered one question per call until the F1 verdict.

    One call = one graph step (ADR-010): each answer_quiz_question resumes
    the pending quiz interrupt and returns the next question; after the
    last answer the graph scores the weighted token F1 against the
    references (threshold 0.60, ADR-009), records progress and reaches
    END — the final payload carries the verdict (done=True), the lesson
    and the quiz result alongside the M1 assessment/route contract.
    """
    server = _server(_confident_replies())
    answers = _quiz_reference_answers()
    calls = [
        ("start_session", {"student": "unit_mcp"}),
        (
            "answer_calibration",
            {
                "student": "unit_mcp",
                "answer": "specs/ — стабильные спеки, changes/ — предложения",
            },
        ),
    ]
    calls += [
        ("answer_quiz_question", {"student": "unit_mcp", "answer": answer})
        for answer in answers
    ]
    payloads = _call_tools(server, calls)

    assert len(payloads) == 2 + len(answers)
    # every intermediate payload is the next pending quiz question
    for payload in payloads[1:-1]:
        assert payload["type"] == "question"
        assert payload["question_kind"] == "quiz"
        assert payload["question"]
        assert payload["done"] is False

    verdict = payloads[-1]
    assert verdict["type"] == "result"
    assert verdict["done"] is True
    # the M1 contract is preserved in the final payload
    assert verdict["assessment"]["level"] == "partial"
    assert verdict["route"]["path"] == "partial"
    # the F1 quiz verdict (ADR-009: weighted score, threshold 0.60)
    assert verdict["quiz"]["domain"] == "openspec-basics"
    assert verdict["quiz"]["passed"] is True
    assert verdict["quiz"]["score"] >= 0.60
    assert verdict["quiz"]["feedback"]
    # the lesson unfolded by the teach node travels to the client too
    assert verdict["lesson"] == LESSON_TEXT
    # the session log carries the F1 verdict and the recorded progress
    assert any("\u043f\u043e\u0440\u043e\u0433 0.60" in entry for entry in verdict["log"])
    assert any("\u041f\u0440\u043e\u0433\u0440\u0435\u0441\u0441" in entry for entry in verdict["log"])


def test_quiz_survives_server_restart_midway():
    """A mid-quiz restart continues from the pending question (ADR-008).

    The tools are stateless — the checkpoint IS the state: after two quiz
    answers a fresh server over the same saver continues the quiz from
    question 3 and reaches the same verdict. The restarted server gets an
    EMPTY fake LLM: quiz stepping is deterministic (no LLM calls — ADR-009),
    so any model call would pop from the empty list and fail loudly.
    """
    checkpointer = InMemorySaver()
    first = _server(_confident_replies(), checkpointer=checkpointer)
    answers = _quiz_reference_answers()
    payloads = _call_tools(
        first,
        [
            ("start_session", {"student": "unit_mcp"}),
            (
                "answer_calibration",
                {"student": "unit_mcp", "answer": "specs/ и changes/"},
            ),
            (
                "answer_quiz_question",
                {"student": "unit_mcp", "answer": answers[0]},
            ),
        ],
    )
    assert payloads[-1]["question_kind"] == "quiz"  # question 2 is pending

    second = _server([], checkpointer=checkpointer)  # no LLM replies needed
    rest = _call_tools(
        second,
        [
            (
                "answer_quiz_question",
                {"student": "unit_mcp", "answer": answer},
            )
            for answer in answers[1:]
        ],
    )
    verdict = rest[-1]
    assert verdict["type"] == "result"
    assert verdict["done"] is True
    assert verdict["quiz"]["passed"] is True
    assert verdict["quiz"]["score"] >= 0.60


def test_quiz_tools_guard_the_state_machine():
    """Quiz guards: wrong tool for the pending kind names the right one.

    answer_quiz_question without a session, answer_calibration on a
    pending quiz question and answer_quiz_question on a pending
    calibration each return an error payload naming the right tool — the
    checkpoint is never fed an answer through the wrong interrupt.
    """
    server = _server(_confident_replies())
    (no_session,) = _call_tools(
        server,
        [("answer_quiz_question", {"student": "ghost", "answer": "..."})],
    )
    assert no_session["type"] == "error"
    assert "start_session" in no_session["message"]

    payloads = _call_tools(
        server,
        [
            ("start_session", {"student": "unit_mcp"}),
            (
                "answer_calibration",
                {"student": "unit_mcp", "answer": "specs/ и changes/"},
            ),
        ],
    )
    assert payloads[1]["question_kind"] == "quiz"  # quiz is pending now
    (wrong_tool,) = _call_tools(
        server,
        [
            (
                "answer_calibration",
                {"student": "unit_mcp", "answer": "не тот инструмент"},
            )
        ],
    )
    assert wrong_tool["type"] == "error"
    assert "answer_quiz_question" in wrong_tool["message"]

    other = _server(_confident_replies())
    _call_tools(other, [("start_session", {"student": "unit_mcp"})])
    (wrong_kind,) = _call_tools(
        other,
        [
            (
                "answer_quiz_question",
                {"student": "unit_mcp", "answer": "не тот инструмент"},
            )
        ],
    )
    assert wrong_kind["type"] == "error"
    assert "answer_calibration" in wrong_kind["message"]
