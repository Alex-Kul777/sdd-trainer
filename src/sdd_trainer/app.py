"""FastAPI HTTP interface — one process, two protocols (ADR-001, issue #13).

ADR-001 finally followed to the letter: a single FastAPI process serves the
REST API and the MCP Streamable HTTP endpoint together. The FastMCP server
(:mod:`sdd_trainer.mcp.server`, ADR-010) is not a separate service — its
``streamable_http_app()`` is mounted at ``/mcp`` on the same application,
over the same graph, checkpointer and LLM. The stdio server
(``python -m sdd_trainer.mcp``) remains the fallback transport (ADR-010).

Mount mechanics (verified against mcp==1.27.1):

- ``FastMCP.streamable_http_app()`` exists under exactly that name and
  returns a Starlette app whose single route lives at
  ``settings.streamable_http_path`` (SDK default ``/mcp``). The factory
  rewrites it to ``/`` before generating the app, so after
  ``app.mount("/mcp", ...)`` the protocol endpoint is ``POST /mcp/`` and
  the bare ``/mcp`` 307-redirects there — standard trailing-slash
  behaviour every Streamable HTTP client follows.
- Starlette does not run mounted sub-apps' lifespans, so the FastAPI app
  adopts the mounted app's lifespan context: under uvicorn (or a TestClient
  context) it starts and stops the Streamable HTTP session manager.
- The SDK ships with DNS-rebinding protection enabled and an *empty*
  allowlist — every Host would be rejected. The factory configures
  ``transport_security`` for localhost (the trainer is a local service;
  OpenClaw connects to ``http://localhost:<port>`` per ADR-001).

REST semantics mirror the MCP session tools (ADR-010: one call = one graph
step): ``POST /sessions/{student}/start`` returns the calibration question,
``POST /sessions/{student}/answer`` resumes the graph with
``Command(resume=...)`` and returns the next interrupt payload or the final
verdict, ``GET /health`` answers liveness. The thread id is
``student:<name>`` (ADR-008) and the state lives in the caller's
checkpointer — the endpoints are stateless, the checkpoint IS the state.
State-machine problems travel as ``{"type": "error", ...}`` payloads with
HTTP 200, exactly like the MCP tools' error results: the payload's
``type`` field carries the semantics, not the status code.

``GET /sessions/{student}/stream`` is the streaming mode of the AIA_07
course pattern: graph events arrive over SSE (``text/event-stream``) as
each node completes (``event: node``), and the stream closes on the next
interrupt (``event: question``) or on END (``event: result``). The
human-in-the-loop half of the pattern: ``?answer=...`` resumes the pending
question with ``Command(resume=...)`` and streams the continuation — an
``EventSource``-style client can run a whole lesson without the sync
endpoints.

The core (graph, tools, memory) is not rewritten: the step engine reuses
the console entry's battle-tested helpers (``student_thread_id``,
``has_pending_session``, ``find_pending_question``) and the MCP layer's
interrupt classification (``_question_kind`` — imported, not copied). The
REST payloads are field-for-field the MCP tools' payloads (spec
http-trainer: «the responses match the MCP tools' payloads for the same
thread»); the parity is pinned by a unit test driving both transports
with the same fake LLM.

Run with ``python -m sdd_trainer.app`` (REST + MCP on one port); the
stdio fallback stays ``python -m sdd_trainer.mcp``.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Callable, Iterator, Optional

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from openai import OpenAIError
from pydantic import BaseModel

from sdd_trainer import __version__
from sdd_trainer.__main__ import (
    find_pending_question,
    has_pending_session,
    student_thread_id,
)
from sdd_trainer.config import GigaChatConfig, trainer_config
from sdd_trainer.core.graph import build_graph
from sdd_trainer.core.llm_manager import LLMManager, StructuredOutputError
from sdd_trainer.core.memory import MemoryManager, TrainingStateStore
from sdd_trainer.core.prompts import ASSESSMENT_DOMAIN
from sdd_trainer.mcp import create_server
from sdd_trainer.mcp.server import _question_kind  # single source of truth
from sdd_trainer.models import RepoAnalysis

#: Hosts the mounted MCP endpoint trusts (DNS-rebinding protection, mcp
#: SDK): the trainer is a local service, so localhost in all its shapes —
#: bare and with any port — is the intended audience (ADR-001: OpenClaw
#: connects to a localhost url).
_ALLOWED_HOSTS = [
    "localhost", "localhost:*",
    "127.0.0.1", "127.0.0.1:*",
    "[::1]", "[::1]:*",
]
_ALLOWED_ORIGINS = [
    "http://localhost", "http://localhost:*",
    "http://127.0.0.1", "http://127.0.0.1:*",
]

#: Error message for a step that died mid-flight (parity with the MCP
#: layer): the checkpoint keeps the last completed step, a retry is safe.
_STEP_FAILED = (
    "Шаг не завершён ({}: {}); чекпоинт хранит последний завершённый "
    "шаг — повтори вызов."
)


class StartRequest(BaseModel):
    """Body of ``POST /sessions/{student}/start`` (both fields optional)."""

    repo_path: Optional[str] = None


class AnswerRequest(BaseModel):
    """Body of ``POST /sessions/{student}/answer`` — the student's answer."""

    answer: str


def _payload(
    *,
    type_: str,
    student: str,
    thread_id: Optional[str],
    resumed: bool = False,
    question: Optional[str] = None,
    question_kind: Optional[str] = None,
    values: Optional[dict] = None,
    done: bool = False,
    message: Optional[str] = None,
) -> dict:
    """Build the uniform endpoint payload — the MCP-layer contract verbatim.

    ``values`` is the graph state (snapshot or invoke result): the
    assessment verdict, the selected route and the session log travel to
    the client unchanged. Field-for-field parity with the MCP tools'
    payloads is what the spec (http-trainer) requires — do not diverge.
    """
    values = values or {}
    return {
        "type": type_,
        "student": student,
        "thread_id": thread_id,
        "resumed": resumed,
        "question_kind": question_kind,
        "question": question,
        "assessment": values.get("assessment") or None,
        "route": values.get("route") or None,
        "lesson": values.get("teach_output") or None,
        "quiz": values.get("quiz_result") or None,
        "log": list(values.get("log") or []),
        "done": done,
        "message": message,
    }


def create_app(
    llm: LLMManager,
    *,
    checkpointer: BaseCheckpointSaver,
    state_store: Optional[TrainingStateStore] = None,
    docs_search: Optional[Callable[[str], list[dict]]] = None,
    repo_analyzer: Optional[Callable[[str], RepoAnalysis]] = None,
) -> FastAPI:
    """Assemble the single-process app: REST + mounted MCP (ADR-001).

    Args:
        llm: the LLM client the graph nodes use — the single test seam
            (unit tests inject a fake OpenAI client; the entry point wires
            the real GigaChat). Shared by both transports.
        checkpointer: persistence for session state (ADR-008) — required:
            a graph with ``interrupt`` cannot run without one. Shared by
            both transports, so a session started over REST continues over
            MCP and vice versa.
        state_store: training-state persistence for the quiz node;
            defaults to the real store inside ``build_graph``.
        docs_search: the fresh-docs tool seam (teach node).
        repo_analyzer: the repo-scan tool seam (passive assessment).

    Returns:
        A :class:`fastapi.FastAPI` application serving the REST endpoints
        and the MCP Streamable HTTP endpoint at ``/mcp`` — one process,
        one port, two protocols.
    """
    # The same FastMCP server (ADR-010) provides the mounted transport:
    # one graph, one checkpointer, both protocols. Its per-transport
    # repo_path cache is separate from the REST layer's — a session
    # started via REST with repo_path degrades to a self-report
    # assessment if continued via MCP, the documented degradation path.
    mcp_server: FastMCP = create_server(
        llm,
        checkpointer=checkpointer,
        state_store=state_store,
        docs_search=docs_search,
        repo_analyzer=repo_analyzer,
    )

    #: repo_path of each session, remembered from /start so the resumed
    #: assess node re-runs the passive scan with the same repo (the node
    #: re-executes on resume). In-memory only — same trade-off as the
    #: MCP layer's cache.
    thread_repos: dict[str, Optional[str]] = {}

    def _build_graph(thread_id: str):
        """Compile the trainer graph for one student's thread."""
        return build_graph(
            llm,
            checkpointer=checkpointer,
            state_store=state_store,
            docs_search=docs_search,
            repo_analyzer=repo_analyzer,
            repo_path=thread_repos.get(thread_id),
        )

    def _step_payload(
        student: str,
        thread_id: str,
        result: dict,
        *,
        resumed: bool = False,
    ) -> dict:
        """Render one finished graph step: interrupt payload or final result.

        The invoke collected events up to the next ``interrupt`` (ADR-010):
        with a pending interrupt the client gets the question plus the
        verdict/route accumulated so far; without one the graph reached
        END and the payload is the final result.
        """
        graph = _build_graph(thread_id)
        snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
        interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
        if interrupts:
            return _payload(
                type_="question",
                student=student,
                thread_id=thread_id,
                resumed=resumed,
                question=interrupts[0].value,
                question_kind=_question_kind(snapshot),
                values=snapshot.values,
            )
        return _payload(
            type_="result",
            student=student,
            thread_id=thread_id,
            resumed=resumed,
            values=snapshot.values,
            done=True,
            message="Сеанс завершён — граф дошёл до конца.",
        )

    # --- the MCP mount (ADR-001): streamable_http_app() → app.mount ---

    mcp_server.settings.streamable_http_path = "/"
    mcp_server.settings.transport_security = TransportSecuritySettings(
        allowed_hosts=_ALLOWED_HOSTS,
        allowed_origins=_ALLOWED_ORIGINS,
    )
    mcp_app = mcp_server.streamable_http_app()
    app = FastAPI(
        title="SDD Trainer",
        version=__version__,
        # Starlette never runs mounted sub-apps' lifespans — adopt the
        # mounted app's context so the Streamable HTTP session manager
        # starts and stops with this process (as under uvicorn).
        lifespan=mcp_app.router.lifespan_context,
    )
    app.mount("/mcp", mcp_app)

    # --- REST: the sync session endpoints (ADR-010 step semantics) ---

    @app.get("/health")
    def health() -> dict:
        """Liveness probe: status ok plus the trainer version (spec scenario)."""
        return {"status": "ok", "version": __version__}

    @app.post("/sessions/{student}/start")
    def start_session(student: str, start: StartRequest | None = None) -> dict:
        """Начать сеанс: задать калибровочный вопрос (или возобновить сеанс).

        Тот же шаг графа, что и MCP-инструмент start_session: новый сеанс
        идёт от START до interrupt узла assess, незавершённый — отдаёт
        сохранённый вопрос с resumed=true. repo_path (необязательно) —
        путь к репозиторию ученика для пассивной оценки.
        """
        try:
            thread_id = student_thread_id(student)
        except ValueError as exc:
            return _payload(
                type_="error", student=student, thread_id=None, message=str(exc)
            )
        thread_repos[thread_id] = start.repo_path if start else None
        graph = _build_graph(thread_id)
        config = {"configurable": {"thread_id": thread_id}}
        try:
            snapshot = graph.get_state(config)
            if has_pending_session(snapshot):
                question = find_pending_question(snapshot)
                if question is not None:
                    return _payload(
                        type_="question",
                        student=student,
                        thread_id=thread_id,
                        resumed=True,
                        question=question,
                        question_kind=_question_kind(snapshot),
                        values=snapshot.values,
                    )
                # Pending work without a stored question (e.g. a crashed
                # step): continue the graph, as the console does.
                result = graph.invoke(None, config)
            else:
                result = graph.invoke({"domain": ASSESSMENT_DOMAIN}, config)
        except (OpenAIError, StructuredOutputError) as exc:
            return _payload(
                type_="error",
                student=student,
                thread_id=thread_id,
                message=_STEP_FAILED.format(type(exc).__name__, exc),
            )
        return _step_payload(student, thread_id, result)

    @app.post("/sessions/{student}/answer")
    def answer(student: str, body: AnswerRequest) -> dict:
        """Ответить на вопрос сеанса — один шаг графа (Command(resume=...)).

        Единый эндпоинт для всех видов вопросов (калибровка, уточнение,
        квиз): граф сам знает, какой interrupt ожидает ответа. Возвращает
        следующий вопрос или итог сеанса (вердикт квиза, done=true).
        """
        try:
            thread_id = student_thread_id(student)
        except ValueError as exc:
            return _payload(
                type_="error", student=student, thread_id=None, message=str(exc)
            )
        graph = _build_graph(thread_id)
        config = {"configurable": {"thread_id": thread_id}}
        try:
            snapshot = graph.get_state(config)
            if not has_pending_session(snapshot):
                return _payload(
                    type_="error",
                    student=student,
                    thread_id=thread_id,
                    message="Нет незавершённого сеанса — сначала вызови "
                            "POST /sessions/{student}/start.".format(
                                student=student),
                )
            if find_pending_question(snapshot) is None:
                return _payload(
                    type_="error",
                    student=student,
                    thread_id=thread_id,
                    message="Сеанс ждёт продолжения без ответа — вызови "
                            "POST /sessions/{student}/start.".format(
                                student=student),
                )
            result = graph.invoke(Command(resume=body.answer), config)
        except (OpenAIError, StructuredOutputError) as exc:
            return _payload(
                type_="error",
                student=student,
                thread_id=thread_id,
                message=_STEP_FAILED.format(type(exc).__name__, exc),
            )
        return _step_payload(student, thread_id, result)

    # --- REST: the SSE streaming mode (AIA_07) ---

    @app.get("/sessions/{student}/stream")
    def stream_session(student: str, answer: Optional[str] = None) -> StreamingResponse:
        """SSE-стриминг событий графа; ?answer=... возобновляет вопрос.

        Стриминговый режим AIA_07: события узлов приходят инкрементально
        (event: node), стрим закрывается на следующем вопросе (event:
        question) или на конце графа (event: result). С ?answer — HITL-шаг:
        Command(resume=answer) + стриминг продолжения.
        """
        return StreamingResponse(
            _sse_events(student, answer), media_type="text/event-stream"
        )

    def _sse_events(student: str, answer: Optional[str]) -> Iterator[str]:
        """Yield the session's graph events as SSE blocks (sync generator).

        FastAPI iterates sync generators in its threadpool, so the
        blocking ``graph.stream`` calls never stall the event loop. State
        machine problems become ``event: error`` blocks — the client
        always gets a well-formed stream instead of a broken connection.
        """

        def event(name: str, data: dict) -> str:
            return "event: {}\ndata: {}\n\n".format(
                name, json.dumps(data, ensure_ascii=False, default=str)
            )

        try:
            thread_id = student_thread_id(student)
        except ValueError as exc:
            yield event(
                "error",
                _payload(
                    type_="error", student=student, thread_id=None,
                    message=str(exc),
                ),
            )
            return
        graph = _build_graph(thread_id)
        config = {"configurable": {"thread_id": thread_id}}
        try:
            resumed = False
            if answer is not None:
                # HITL half of the AIA_07 pattern: resume the pending
                # question and stream the continuation.
                snapshot = graph.get_state(config)
                if not has_pending_session(snapshot):
                    yield event(
                        "error",
                        _payload(
                            type_="error", student=student, thread_id=thread_id,
                            message="Нет незавершённого сеанса — сначала "
                                    "вызови POST /sessions/{student}/start."
                                    .format(student=student),
                        ),
                    )
                    return
                if find_pending_question(snapshot) is None:
                    yield event(
                        "error",
                        _payload(
                            type_="error", student=student, thread_id=thread_id,
                            message="Сеанс ждёт продолжения без ответа — "
                                    "вызови POST /sessions/{student}/start."
                                    .format(student=student),
                        ),
                    )
                    return
                stream_input = Command(resume=answer)
                resumed = True
            else:
                snapshot = graph.get_state(config)
                if has_pending_session(snapshot):
                    question = find_pending_question(snapshot)
                    if question is not None:
                        # Nothing to run: the pending question is the news.
                        yield event(
                            "question",
                            _payload(
                                type_="question", student=student,
                                thread_id=thread_id, resumed=True,
                                question=question,
                                question_kind=_question_kind(snapshot),
                                values=snapshot.values,
                            ),
                        )
                        return
                    stream_input = None
                else:
                    stream_input = {"domain": ASSESSMENT_DOMAIN}
            for update in graph.stream(stream_input, config, stream_mode="updates"):
                if isinstance(update, dict) and "__interrupt__" in update:
                    break  # the question event below closes the stream
                for node, delta in (update or {}).items():
                    yield event("node", {"node": node, "update": delta})
            snapshot = graph.get_state(config)
            question = find_pending_question(snapshot)
            if question is not None:
                yield event(
                    "question",
                    _payload(
                        type_="question", student=student, thread_id=thread_id,
                        resumed=resumed, question=question,
                        question_kind=_question_kind(snapshot),
                        values=snapshot.values,
                    ),
                )
            else:
                yield event(
                    "result",
                    _payload(
                        type_="result", student=student, thread_id=thread_id,
                        resumed=resumed, values=snapshot.values, done=True,
                        message="Сеанс завершён — граф дошёл до конца.",
                    ),
                )
        except (OpenAIError, StructuredOutputError) as exc:
            yield event(
                "error",
                _payload(
                    type_="error", student=student, thread_id=thread_id,
                    message=_STEP_FAILED.format(type(exc).__name__, exc),
                ),
            )

    return app


def main() -> None:
    """Wire the real trainer and serve REST + MCP on one port (ADR-001).

    ``python -m sdd_trainer.app`` — GigaChat via the cloud.ru endpoint
    (ADR-005), ``SqliteSaver`` checkpoints (ADR-008), uvicorn in front.
    Host/port default to localhost:8000 (the trainer is a local service);
    override with SDD_TRAINER_HOST / SDD_TRAINER_PORT.
    """
    import uvicorn

    config = GigaChatConfig()
    if not config.is_configured():
        print(
            "SDD Trainer HTTP: не найден ключ GIGACHAT_KEY. "
            "Скопируйте .env.example в .env и заполните ключ cloud.ru (ADR-005).",
            file=sys.stderr,
        )
        sys.exit(1)

    memory = MemoryManager(checkpoint_path=trainer_config.checkpoint_path)
    llm = LLMManager(config=config)
    application = create_app(llm, checkpointer=memory.get_checkpointer())
    try:
        uvicorn.run(
            application,
            host=os.getenv("SDD_TRAINER_HOST", "127.0.0.1"),
            port=int(os.getenv("SDD_TRAINER_PORT", "8000")),
        )
    finally:
        memory.close()


if __name__ == "__main__":
    main()
