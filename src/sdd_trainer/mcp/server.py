"""FastMCP server exposing the trainer graph over MCP (ADR-010, issue #9).

Transport: stdio (``python -m sdd_trainer.mcp``) — the standard for local
MCP servers; the server is a thin wrapper, the core (graph, tools, memory)
is not rewritten. Session tools advance the checkpointed graph one step
per call — resume with the student's answer, collect events up to the next
``interrupt``, return its payload (ADR-010: один вызов = один шаг графа).
The thread id is ``student:<name>`` (ADR-008) and the state lives in the
existing ``SqliteSaver`` — restart resilience comes for free.

stdout belongs to the MCP protocol: nothing in this package may print to
stdout (diagnostics go to stderr via ``logging``); the graph nodes already
follow that rule — the console's ``[граф]`` prints live in ``__main__.py``
glue, which the MCP server does not use.
"""
from __future__ import annotations

from typing import Callable, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from mcp.server.fastmcp import FastMCP

from sdd_trainer.core.llm_manager import LLMManager
from sdd_trainer.core.memory import TrainingStateStore
from sdd_trainer.models import RepoAnalysis

#: Server name announced in the MCP initialize handshake (ADR-010).
SERVER_NAME = "sdd-trainer"


def create_server(
    llm: LLMManager,
    *,
    checkpointer: BaseCheckpointSaver,
    state_store: Optional[TrainingStateStore] = None,
    docs_search: Optional[Callable[[str], list[dict]]] = None,
    repo_analyzer: Optional[Callable[[str], RepoAnalysis]] = None,
) -> FastMCP:
    """Assemble the FastMCP server over the trainer graph (task 1.1).

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
    return server
