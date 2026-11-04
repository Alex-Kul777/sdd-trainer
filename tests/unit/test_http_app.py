"""Unit tests for the FastAPI HTTP interface (ADR-001, issue #13, tasks 2.1-2.5).

The seam is the same as in the graph / MCP-server unit tests: a real FastAPI
application whose ``LLMManager`` is wired to a fake OpenAI client — no
network. Starlette's ``TestClient`` carries the actual HTTP protocol, so
every request exercises the full path: FastAPI route → step engine →
compiled graph → checkpointer → payload. The MCP mount is proven through
the mounted endpoint itself: a real Streamable HTTP initialize handshake
inside the ``TestClient`` lifespan (the session manager runs exactly as it
does under uvicorn).

Payload parity with the MCP tools is asserted literally (spec http-trainer:
«the responses match the MCP tools' payloads for the same thread»): the
same fake replies and student name are driven through the in-memory MCP
transport and through REST, and the resulting payload dicts must be equal.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest
from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver
from mcp.shared.memory import create_connected_server_and_client_session
from starlette.testclient import TestClient

from sdd_trainer import __version__
from sdd_trainer.config import GigaChatConfig
from sdd_trainer.core.llm_manager import LLMManager
from sdd_trainer.core.memory import TrainingStateStore
from sdd_trainer.mcp import create_server
from sdd_trainer.app import create_app

pytestmark = pytest.mark.unit


# --- fake OpenAI client (the same seam as test_graph / test_mcp_server) ---

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


def _quiz_reference_answers(domain: str = "openspec-basics") -> list[str]:
    """Reference answers from the authored quiz data (deterministic F1 = 1)."""
    from sdd_trainer.lessons import load_quiz

    return [q.reference_answer for q in load_quiz(domain).questions]


def _app(replies: list, checkpointer=None, **seams) -> FastAPI:
    """Build the FastAPI app over a fake LLM (no network, in-memory checkpoint).

    The training-state store points at a throwaway temp file: unit tests
    must never touch the repo's runtime ``data/training-state.json``.
    ``seams`` forwards the create_app injection points (docs_search,
    repo_analyzer) — the same discipline as the graph tests.
    """
    llm = LLMManager(config=GigaChatConfig(api_key="test"), client=FakeOpenAI(replies))
    state_store = TrainingStateStore(
        path=Path(tempfile.mkdtemp()) / "training-state.json"
    )
    return create_app(
        llm,
        checkpointer=checkpointer or InMemorySaver(),
        state_store=state_store,
        docs_search=seams.get("docs_search"),
        repo_analyzer=seams.get("repo_analyzer"),
    )


def _parse_sse(text: str) -> list[dict]:
    """Parse an SSE body into ``[{"event": name, "data": dict}, ...]``."""
    events = []
    for block in text.split("\n\n"):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        parsed = {}
        for line in lines:
            if line.startswith("event: "):
                parsed["event"] = line[len("event: "):]
            elif line.startswith("data: "):
                parsed["data"] = json.loads(line[len("data: "):])
        events.append(parsed)
    return events


def _mcp_call_tools(server, tool_calls: list[tuple[str, dict]]) -> list[dict]:
    """Drive the MCP server through the SDK's in-memory transport (parity seam)."""
    async def scenario():
        results = []
        async with create_connected_server_and_client_session(server) as session:
            await session.initialize()
            for name, arguments in tool_calls:
                results.append(await session.call_tool(name, arguments))
        return results

    results = anyio.run(scenario)
    payloads = []
    for result in results:
        assert not result.isError, f"tool call failed: {result.content}"
        payloads.append(json.loads(result.content[0].text))
    return payloads


#: A minimal MCP initialize request for the mounted Streamable HTTP endpoint.
_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "unit-test", "version": "0.0"},
    },
}

#: Headers a Streamable HTTP client sends (the SDK requires both Accept
#: types on POST; the Host must be trusted by the DNS-rebinding guard).
_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Host": "localhost",
}


# --- 2.3: health and the sync session endpoints ---

def test_health_reports_ok_and_version():
    """GET /health answers status ok plus the trainer version (spec scenario)."""
    client = TestClient(_app(_confident_replies()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_start_returns_calibration_question():
    """POST start on a fresh thread returns the calibration question.

    Same contract as the MCP start_session tool (ADR-010: one call = one
    graph step): the graph runs from START up to the assess interrupt and
    the response carries that interrupt's payload under the student's
    thread id (ADR-008) — no verdict yet (the LLM is called only after
    the answer, so the fake client stays untouched).
    """
    from sdd_trainer.core.prompts import CALIBRATION_QUESTION

    client = TestClient(_app(_confident_replies()))

    response = client.post("/sessions/unit_http/start")

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "question"
    assert payload["question_kind"] == "calibration"
    assert payload["question"] == CALIBRATION_QUESTION
    assert payload["student"] == "unit_http"
    assert payload["thread_id"] == "student:unit_http"
    assert payload["resumed"] is False
    assert payload["done"] is False
    assert payload["assessment"] is None
    assert payload["route"] is None


def test_start_with_invalid_student_name_is_error():
    """An invalid student name returns the error payload, not a crash.

    The thread-id convention (ADR-008) is enforced by the same helper as
    the console and MCP layers; the response mirrors the MCP tool's error
    payload instead of an unhandled 500.
    """
    client = TestClient(_app(_confident_replies()))

    response = client.post("/sessions/two%20words/start")

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "error"
    assert "недопустимое имя" in payload["message"]


def test_answer_resumes_graph_to_quiz_question():
    """POST answer resumes the graph with Command(resume=...) — one step.

    The answer resumes the assess node; the graph runs assess → route →
    teach → quiz and stops at the first quiz question. The response
    carries the assessment verdict, the selected route and the pending
    question — the same step the MCP answer_calibration tool performs.
    """
    client = TestClient(_app(_confident_replies(level="partial", confidence=0.9)))
    client.post("/sessions/unit_http/start")

    response = client.post(
        "/sessions/unit_http/answer",
        json={"answer": "specs/ — стабильные спеки, changes/ — предложения"},
    )

    assert response.status_code == 200
    verdict = response.json()
    assert verdict["type"] == "question"
    assert verdict["question_kind"] == "quiz"
    assert verdict["question"]  # the first quiz question is pending
    assert verdict["assessment"]["level"] == "partial"
    assert verdict["assessment"]["confidence"] == 0.9
    assert verdict["route"]["path"] == "partial"
    assert verdict["done"] is False
    assert any("Оценка: partial" in entry for entry in verdict["log"])
    assert any("Маршрут: partial" in entry for entry in verdict["log"])


def test_answer_without_pending_session_is_error():
    """Answering without a session returns an error payload naming start.

    The state-machine guard mirrors the MCP tools: the checkpoint is the
    only state, and an answer can never be fed into a nonexistent
    interrupt.
    """
    client = TestClient(_app(_confident_replies()))

    response = client.post("/sessions/ghost/answer", json={"answer": "..."})

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "error"
    assert "start" in payload["message"]


def test_full_session_over_rest_reaches_f1_verdict():
    """A whole session drives over REST: start → answer → … → F1 verdict.

    The unified answer endpoint steps through every question kind
    (calibration, then each quiz question): after the last answer the
    graph scores the weighted token F1 (threshold 0.60, ADR-009), records
    progress and reaches END — done=True with the verdict, lesson and
    quiz result.
    """
    client = TestClient(_app(_confident_replies()))
    answers = _quiz_reference_answers()

    payloads = [client.post("/sessions/unit_http/start").json()]
    payloads.append(
        client.post(
            "/sessions/unit_http/answer",
            json={"answer": "specs/ и changes/"},
        ).json()
    )
    for answer in answers:
        payloads.append(
            client.post(
                "/sessions/unit_http/answer",
                json={"answer": answer},
            ).json()
        )

    # every intermediate payload is the next pending question
    for payload in payloads[:-1]:
        assert payload["type"] == "question"
        assert payload["question"]
        assert payload["done"] is False

    verdict = payloads[-1]
    assert verdict["type"] == "result"
    assert verdict["done"] is True
    assert verdict["assessment"]["level"] == "partial"
    assert verdict["route"]["path"] == "partial"
    assert verdict["quiz"]["domain"] == "openspec-basics"
    assert verdict["quiz"]["passed"] is True
    assert verdict["quiz"]["score"] >= 0.60
    assert verdict["lesson"] == LESSON_TEXT


# --- payload parity with the MCP tools (spec: http-trainer) ---

def test_rest_payloads_match_mcp_tool_payloads():
    """REST responses are byte-for-byte the MCP tools' payloads (spec scenario).

    The same fake replies and student name are driven through the SDK's
    in-memory MCP transport and through REST; the payload dicts must be
    equal — the HTTP layer is a second transport over the same step
    engine, not a divergent copy of the contract.
    """
    student = "unit_parity"
    answer = "specs/ — стабильные спеки, changes/ — предложения"

    mcp_server = create_server(
        LLMManager(
            config=GigaChatConfig(api_key="test"),
            client=FakeOpenAI(_confident_replies()),
        ),
        checkpointer=InMemorySaver(),
        state_store=TrainingStateStore(
            path=Path(tempfile.mkdtemp()) / "training-state.json"
        ),
    )
    mcp_payloads = _mcp_call_tools(
        mcp_server,
        [
            ("start_session", {"student": student}),
            ("answer_calibration", {"student": student, "answer": answer}),
        ],
    )

    client = TestClient(_app(_confident_replies()))
    rest_start = client.post(f"/sessions/{student}/start").json()
    rest_answer = client.post(
        f"/sessions/{student}/answer", json={"answer": answer}
    ).json()

    assert rest_start == mcp_payloads[0]
    assert rest_answer == mcp_payloads[1]


def test_start_resumes_pending_question_after_restart():
    """A fresh app over the same checkpointer resumes the pending question.

    The endpoints are stateless — the checkpoint IS the state (ADR-008):
    after a "restart" (a fresh create_app over the same saver) the same
    student gets the same pending calibration question with resumed=True.
    """
    from sdd_trainer.core.prompts import CALIBRATION_QUESTION

    checkpointer = InMemorySaver()
    first = TestClient(_app(_confident_replies(), checkpointer=checkpointer))
    payload = first.post("/sessions/unit_http/start").json()
    assert payload["resumed"] is False

    second = TestClient(_app(_confident_replies(), checkpointer=checkpointer))
    resumed = second.post("/sessions/unit_http/start").json()
    assert resumed["type"] == "question"
    assert resumed["resumed"] is True
    assert resumed["question_kind"] == "calibration"
    assert resumed["question"] == CALIBRATION_QUESTION


# --- 2.4: SSE streaming (AIA_07: streaming + HITL via interrupt/Command) ---

def test_stream_starts_session_with_calibration_question():
    """GET stream on a fresh thread is SSE ending in the calibration question.

    The streaming mode (AIA_07) starts the session like the sync endpoint
    but delivers the graph's events over ``text/event-stream``; on a fresh
    thread the assess node interrupts before any node completes, so the
    stream carries the question event.
    """
    from sdd_trainer.core.prompts import CALIBRATION_QUESTION

    client = TestClient(_app(_confident_replies()))

    response = client.get("/sessions/unit_http/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    assert events, "the stream must carry at least one SSE event"
    final = events[-1]
    assert final["event"] == "question"
    assert final["data"]["type"] == "question"
    assert final["data"]["question_kind"] == "calibration"
    assert final["data"]["question"] == CALIBRATION_QUESTION
    assert final["data"]["thread_id"] == "student:unit_http"
    assert final["data"]["resumed"] is False


def test_stream_with_answer_emits_node_events_incrementally():
    """stream?answer=... resumes with Command and streams node events in order.

    The HITL streaming loop (AIA_07): the calibration answer resumes the
    graph and each completed node arrives as its own SSE event — assess,
    route, teach — before the stream closes on the quiz interrupt. The
    session state persists in the checkpointer: the next sync answer
    continues the quiz from the pending question.
    """
    client = TestClient(_app(_confident_replies()))
    client.post("/sessions/unit_http/start")

    response = client.get(
        "/sessions/unit_http/stream",
        params={"answer": "specs/ — стабильные спеки, changes/ — предложения"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)

    node_events = [e for e in events if e["event"] == "node"]
    assert [e["data"]["node"] for e in node_events] == ["assess", "route", "teach"]
    # each node's update travels with the event (incremental payloads)
    teach_event = node_events[-1]
    assert teach_event["data"]["update"]["teach_output"] == LESSON_TEXT

    final = events[-1]
    assert final["event"] == "question"
    assert final["data"]["question_kind"] == "quiz"
    assert final["data"]["resumed"] is True
    assert final["data"]["assessment"]["level"] == "partial"

    # the checkpoint holds the pending quiz question: the session continues
    answers = _quiz_reference_answers()
    continuation = client.post(
        "/sessions/unit_http/answer", json={"answer": answers[0]}
    ).json()
    assert continuation["type"] == "question"
    assert continuation["question_kind"] == "quiz"


def test_stream_replays_pending_question_during_lesson():
    """Opening the stream mid-lesson replays the pending question (spec scenario).

    A client that opens the stream endpoint while the session waits at a
    question gets that question immediately (resumed=True) — the
    checkpoint holds the session state, nothing is re-run and no LLM call
    is made.
    """
    from sdd_trainer.core.prompts import CALIBRATION_QUESTION

    client = TestClient(_app(_confident_replies()))
    client.post("/sessions/unit_http/start")

    response = client.get("/sessions/unit_http/stream")

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert len(events) == 1
    assert events[0]["event"] == "question"
    assert events[0]["data"]["resumed"] is True
    assert events[0]["data"]["question_kind"] == "calibration"
    assert events[0]["data"]["question"] == CALIBRATION_QUESTION


def test_stream_answer_without_session_emits_error_event():
    """stream?answer=... without a session emits an SSE error event.

    The state-machine guard mirrors the sync endpoints: the client learns
    the problem from the event stream, never from a broken connection.
    """
    client = TestClient(_app(_confident_replies()))

    response = client.get("/sessions/ghost/stream", params={"answer": "..."})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    assert len(events) == 1
    assert events[0]["event"] == "error"
    assert events[0]["data"]["type"] == "error"
    assert "start" in events[0]["data"]["message"]


def test_answer_survives_llm_failure_with_error_payload():
    """An LLM failure mid-step returns an error payload; the checkpoint survives.

    The same contract as the MCP layer: the failed step changes nothing —
    the checkpoint still holds the pending question, so a retry resumes
    from the same interrupt and reaches the verdict.
    """
    from openai import OpenAIError

    # the primary failure is retried once with the fallback model
    # (ADR-005) — both must fail for the error to reach the endpoint
    replies = [OpenAIError("boom"), OpenAIError("boom again")] + _confident_replies()
    client = TestClient(_app(replies))
    client.post("/sessions/unit_http/start")

    failed = client.post(
        "/sessions/unit_http/answer", json={"answer": "..."}
    ).json()

    assert failed["type"] == "error"
    assert "Шаг не завершён" in failed["message"]
    assert failed["thread_id"] == "student:unit_http"

    # the checkpoint still holds the calibration question — retry resumes
    retry = client.post(
        "/sessions/unit_http/answer",
        json={"answer": "specs/ — стабильные спеки, changes/ — предложения"},
    ).json()
    assert retry["type"] == "question"
    assert retry["question_kind"] == "quiz"
    assert retry["assessment"]["level"] == "partial"


# --- 2.5: the MCP mount — one process, two protocols (ADR-001) ---

def test_mcp_endpoint_mounted_and_answers_initialize():
    """The mounted Streamable HTTP endpoint answers a real MCP initialize.

    ADR-001 literally: the FastMCP server's ``streamable_http_app()`` is
    mounted at ``/mcp`` on the same FastAPI process. The TestClient
    lifespan runs the session manager exactly as uvicorn would; the
    initialize handshake travels the full mounted path and announces the
    trainer's MCP server name (ADR-010).
    """
    from starlette.routing import Mount

    app = _app(_confident_replies())
    # the mount is registered on the FastAPI app itself
    assert any(
        isinstance(route, Mount) and route.path == "/mcp" for route in app.routes
    )

    with TestClient(app) as client:
        response = client.post("/mcp/", json=_INITIALIZE, headers=_MCP_HEADERS)

        assert response.status_code == 200
        assert "sdd-trainer" in response.text
        assert response.headers.get("mcp-session-id")  # a session was created

        # the bare /mcp path redirects to the mounted endpoint (trailing
        # slash) — Streamable HTTP clients follow the 307 transparently
        redirect = client.post(
            "/mcp", json=_INITIALIZE, headers=_MCP_HEADERS, follow_redirects=False
        )
        assert redirect.status_code == 307
        assert redirect.headers["location"].endswith("/mcp/")
