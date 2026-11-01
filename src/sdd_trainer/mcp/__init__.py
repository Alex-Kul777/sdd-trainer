"""MCP transport (phase 3): Streamable HTTP endpoint mounted in FastAPI.

``FastMCP.streamable_http_app()`` -> ``app.mount("/mcp")`` — one process
serves REST and MCP (ADR-001); stdio transport (``python -m sdd_trainer.mcp``)
is the fallback. Exposes trainer tools to OpenClaw (ADR-004, ADR-007):

``start_lesson``, ``check_knowledge``, ``get_progress``, ``get_graph_structure``,
``analyze_student_repo``, ``get_student_history``.

Implemented by the ``add-mcp-integration`` change.
"""
