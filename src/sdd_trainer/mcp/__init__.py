"""MCP integration of the SDD Trainer (phase 2, ADR-010, issue #9).

``python -m sdd_trainer.mcp`` serves the trainer as a local MCP server
over stdio (the official Python SDK's FastMCP): any MCP client — Claude
Desktop, Cline, OpenClaw — becomes the student. The server is a thin
wrapper over the existing core (graph, tools, memory — nothing is
rewritten): session tools advance the checkpointed graph one step per
call (ADR-010), with the thread id ``student:<name>`` (ADR-008) and the
state in the existing ``SqliteSaver``.

Session tools (M1, issue #9): ``start_session`` → calibration question,
``answer_calibration`` → assessment verdict + route (or a clarification
question), ``answer_clarification`` → re-assessed verdict + route. Quiz
steps and direct tools arrive in M2 (issue #10).
"""
from sdd_trainer.mcp.server import SERVER_NAME, create_server

__all__ = ["SERVER_NAME", "create_server"]
