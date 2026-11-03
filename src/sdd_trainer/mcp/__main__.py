"""Entry point for ``python -m sdd_trainer.mcp`` — MCP server over stdio (ADR-010).

Wires the real trainer — GigaChat via the cloud.ru endpoint (ADR-005),
``SqliteSaver`` checkpoints at ``data/checkpoints.sqlite`` (ADR-008) — and
serves the session tools over stdio, the standard transport for local MCP
servers. Diagnostics go to stderr: stdout is the MCP protocol stream and
must stay clean (see :mod:`sdd_trainer.mcp.server`).
"""
from __future__ import annotations

import sys

from sdd_trainer.config import GigaChatConfig, trainer_config
from sdd_trainer.core.llm_manager import LLMManager
from sdd_trainer.core.memory import MemoryManager
from sdd_trainer.mcp import create_server


def main() -> None:
    """Wire the real trainer and serve MCP over stdio until the client exits."""
    config = GigaChatConfig()
    if not config.is_configured():
        print(
            "SDD Trainer MCP: не найден ключ GIGACHAT_KEY. "
            "Скопируйте .env.example в .env и заполните ключ cloud.ru (ADR-005).",
            file=sys.stderr,
        )
        sys.exit(1)

    memory = MemoryManager(checkpoint_path=trainer_config.checkpoint_path)
    llm = LLMManager(config=config)
    server = create_server(llm, checkpointer=memory.get_checkpointer())
    try:
        server.run("stdio")
    finally:
        memory.close()


if __name__ == "__main__":
    main()
