"""SDD Trainer — root entry shim (rag_GigaChat convention).

Runs the FastAPI server (REST + SSE + MCP ``/mcp`` in one process, ADR-001):

    python app.py            # same as: python -m sdd_trainer.app

Console trainer (phase 1): ``python -m sdd_trainer``.
"""
from __future__ import annotations

from sdd_trainer.app import main

if __name__ == "__main__":
    main()
