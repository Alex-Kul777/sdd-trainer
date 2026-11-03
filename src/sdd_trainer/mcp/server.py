"""FastMCP server exposing the trainer graph over MCP (ADR-010, issue #9).

Transport: stdio (``python -m sdd_trainer.mcp``) — the standard for local
MCP servers; the server is a thin wrapper, the core (graph, tools, memory)
is not rewritten. Session tools advance the checkpointed graph one step
per call — resume with the student's answer, collect events up to the next
``interrupt``, return its payload (ADR-010: один вызов = один шаг графа).
The thread id is ``student:<name>`` (ADR-008) and the state lives in the
existing ``SqliteSaver`` — restart resilience comes for free.

Step engine: every session tool takes ``student`` (the tools are stateless
— the checkpoint IS the state, so a server restart between calls loses
nothing; this refines the design sketch, which reserves exactly that
freedom: «точный состав сессийных инструментов уточняется реализацией»).
The resume-gate semantics (pending session detection, pending-question
extraction, thread-id convention) are imported from the console entry —
the battle-tested single source of truth from the issue #8 live smoke.

stdout belongs to the MCP protocol: nothing in this package may print to
stdout (diagnostics go to stderr via ``logging``); the graph nodes already
follow that rule — the console's ``[граф]`` prints live in the console
glue, which the MCP server does not use.
"""
from __future__ import annotations

from typing import Callable, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from mcp.server.fastmcp import FastMCP
from openai import OpenAIError

from sdd_trainer.__main__ import (
    find_pending_question,
    has_pending_session,
    student_thread_id,
)
from sdd_trainer.core.graph import build_graph
from sdd_trainer.core.llm_manager import LLMManager, StructuredOutputError
from sdd_trainer.core.memory import TrainingStateStore
from sdd_trainer.core.prompts import ASSESSMENT_DOMAIN
from sdd_trainer.models import RepoAnalysis

#: Server name announced in the MCP initialize handshake (ADR-010).
SERVER_NAME = "sdd-trainer"

#: Mapping of pending graph nodes to the kind of question the client sees.
_QUESTION_KINDS = {"assess": "calibration", "clarify": "clarification", "quiz": "quiz"}

#: The tool that answers each question kind — used in mismatch errors to
#: point the client at the right next call (quiz answering arrives in M2).
_KIND_TOOLS = {
    "calibration": "answer_calibration",
    "clarification": "answer_clarification",
    "quiz": "ответ на вопрос квиза — инструмент появится в M2 (issue #10)",
}


def _question_kind(next_nodes) -> Optional[str]:
    """Classify the pending interrupt by the node that raised it.

    ``snapshot.next`` holds the node about to (re-)execute — the node whose
    ``interrupt`` the student must answer next. Unknown nodes (future
    graph extensions) classify as None; the payload still carries the raw
    question, so the client is never left without information.
    """
    for node in next_nodes or ():
        if node in _QUESTION_KINDS:
            return _QUESTION_KINDS[node]
    return None


def create_server(
    llm: LLMManager,
    *,
    checkpointer: BaseCheckpointSaver,
    state_store: Optional[TrainingStateStore] = None,
    docs_search: Optional[Callable[[str], list[dict]]] = None,
    repo_analyzer: Optional[Callable[[str], RepoAnalysis]] = None,
) -> FastMCP:
    """Assemble the FastMCP server over the trainer graph (tasks 1.1-1.2).

    Args:
        llm: the LLM client the graph nodes use — the single test seam
            (unit tests inject a fake OpenAI client, the same discipline
            as the graph tests; the entry point wires the real GigaChat).
        checkpointer: persistence for session state (ADR-008) — required:
            a graph with ``interrupt`` cannot run without one. The entry
            point wires the ``SqliteSaver`` from ``MemoryManager``; unit
            tests use ``InMemorySaver`` or a temporary ``SqliteSaver``.
        state_store: training-state persistence for the quiz node
            (progress recording); defaults to the real store inside
            ``build_graph``. Unit tests inject a throwaway temp store.
        docs_search: the fresh-docs tool seam (teach node) — unit tests
            inject a fake callable, same as in the graph tests.
        repo_analyzer: the repo-scan tool seam (passive assessment) —
            unit tests inject a fake callable.

    Returns:
        A :class:`~mcp.server.fastmcp.FastMCP` instance ready to serve
        over stdio (``server.run("stdio")``) or to be driven by the SDK's
        in-memory transport in tests.
    """
    server = FastMCP(SERVER_NAME)

    #: repo_path of each session, remembered from start_session so the
    #: resumed assess node re-runs the passive scan with the same repo
    #: (the node re-executes on resume). In-memory only: after a server
    #: restart a mid-assess resume degrades to a self-report assessment —
    #: the graph's documented degradation path.
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
        """Build the uniform tool payload (the MCP-layer contract).

        ``values`` is the graph state (snapshot or invoke result): the
        assessment verdict, the selected route and the session log travel
        to the client verbatim; ``log`` is the full checkpointed log, so
        the payload stays correct across server restarts (the client
        re-renders what it needs).
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
            "log": list(values.get("log") or []),
            "done": done,
            "message": message,
        }

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
                question_kind=_question_kind(snapshot.next),
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

    @server.tool()
    def start_session(student: str, repo_path: str | None = None) -> dict:
        """Начать сеанс тренера SDD/OpenSpec: задать калибровочный вопрос.

        Возобновляет незавершённый сеанс с чекпоинта (тем же учеником) или
        начинает новый. Возвращает калибровочный вопрос (question_kind =
        "calibration"); ответ на него отправляй инструментом
        answer_calibration. repo_path — путь к репозиторию ученика для
        пассивной оценки (необязательно).
        """
        try:
            thread_id = student_thread_id(student)
        except ValueError as exc:
            return _payload(type_="error", student=student, thread_id=None,
                            message=str(exc))
        thread_repos[thread_id] = repo_path
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
                        question_kind=_question_kind(snapshot.next),
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
                message="Шаг не завершён ({}: {}); чекпоинт хранит "
                        "последний завершённый шаг — повтори вызов.".format(
                            type(exc).__name__, exc),
            )
        return _step_payload(student, thread_id, result)

    def _resume_answer(student: str, answer: str, expected_kind: str) -> dict:
        """Resume the pending question with the student's answer (one step).

        State-machine guards first (the checkpoint is the only state): a
        missing session, a pending step without a stored question, or a
        different question kind each return an error payload naming the
        right tool — the client can never feed an answer into the wrong
        interrupt by mistake.
        """
        try:
            thread_id = student_thread_id(student)
        except ValueError as exc:
            return _payload(type_="error", student=student, thread_id=None,
                            message=str(exc))
        graph = _build_graph(thread_id)
        config = {"configurable": {"thread_id": thread_id}}
        try:
            snapshot = graph.get_state(config)
            if not has_pending_session(snapshot):
                return _payload(
                    type_="error", student=student, thread_id=thread_id,
                    message="Нет незавершённого сеанса — сначала вызови "
                            "start_session.",
                )
            question = find_pending_question(snapshot)
            if question is None:
                return _payload(
                    type_="error", student=student, thread_id=thread_id,
                    message="Сеанс ждёт продолжения без ответа — вызови "
                            "start_session.",
                )
            kind = _question_kind(snapshot.next)
            if kind != expected_kind:
                tool = _KIND_TOOLS.get(kind, "start_session")
                return _payload(
                    type_="error", student=student, thread_id=thread_id,
                    message="Сеанс ждёт {}-вопроса — используй {}.".format(
                        kind or "неизвестный", tool),
                )
            result = graph.invoke(Command(resume=answer), config)
        except (OpenAIError, StructuredOutputError) as exc:
            return _payload(
                type_="error", student=student, thread_id=thread_id,
                message="Шаг не завершён ({}: {}); чекпоинт хранит "
                        "последний завершённый шаг — повтори вызов.".format(
                            type(exc).__name__, exc),
            )
        return _step_payload(student, thread_id, result)

    @server.tool()
    def answer_calibration(student: str, answer: str) -> dict:
        """Ответить на калибровочный вопрос сеанса (question_kind = "calibration").

        Возвращает вердикт оценки (level, confidence, justification) и
        выбранный маршрут (path, reason); при низкой уверенности — вместо
        вердикта уточняющий вопрос (question_kind = "clarification"), ответ
        на него отправляй инструментом answer_clarification. Если маршрут
        уже выбран — следующий вопрос квиза (quiz-инструменты — M2, issue #10).
        """
        return _resume_answer(student, answer, "calibration")

    return server
