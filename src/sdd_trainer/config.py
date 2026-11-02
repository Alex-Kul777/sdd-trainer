"""Centralized configuration for SDD Trainer.

Conventions follow the rag_GigaChat sample repo (ADR-002): dataclass-based
config objects, credentials from environment variables, module-level
singletons.

GigaChat is accessed through the OpenAI-compatible cloud.ru API (ADR-005):
the ``openai`` package with a custom ``base_url`` — no ``langchain_gigachat``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Project root: src/sdd_trainer/config.py -> repo root (3 levels up)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Load .env from the repo root if present (never committed, see .gitignore)
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class GigaChatConfig:
    """GigaChat access via the OpenAI-compatible cloud.ru API (ADR-005).

    Attributes:
        api_key: API key from the ``GIGACHAT_KEY`` environment variable,
            read at instantiation (never hardcoded).
        base_url: OpenAI-compatible endpoint of cloud.ru foundation models.
        model: primary chat model for lessons and dialogue.
        fallback_model: fallback reasoning model for when the primary one is
            unavailable (exact ID confirmed via live ``models.list``,
            add-console-trainer task 1.1).
        timeout: request timeout in seconds.
        max_retries: retry count for transient failures.
    """

    api_key: str = field(default_factory=lambda: os.getenv("GIGACHAT_KEY", ""))
    base_url: str = "https://foundation-models.api.cloud.ru/v1"
    model: str = "GigaChat/GigaChat-3-Pro"
    fallback_model: str = "ai-sage/GigaChat3.5-432B-A28B-Reasoning"
    timeout: int = 90
    max_retries: int = 3

    def is_configured(self) -> bool:
        """Return True when an API key is present (no key validation)."""
        return bool(self.api_key)


@dataclass
class TavilyConfig:
    """Tavily search API settings (ADR-006).

    The trainer's ``search_sdd_docs`` tool fetches fresh SDD/OpenSpec
    documentation through Tavily; the key is the existing
    ``TAVILY_API_KEY`` secret (no new registration, ADR-006).

    Attributes:
        api_key: API key from the ``TAVILY_API_KEY`` environment variable,
            read at instantiation (never hardcoded).
        base_url: Tavily search API endpoint.
        max_results: number of results requested per search.
        timeout: request timeout in seconds.
    """

    api_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))
    base_url: str = "https://api.tavily.com"
    max_results: int = 5
    timeout: int = 30

    def is_configured(self) -> bool:
        """Return True when an API key is present (no key validation)."""
        return bool(self.api_key)


@dataclass
class TrainerConfig:
    """Trainer-wide paths and settings (ADR-008).

    Attributes:
        data_dir: directory for runtime data (training state, checkpoints).
        prompts_dir: directory with few-shot lesson prompt skeletons.
        training_state_path: student progress across the 6 SDD domains.
        checkpoint_path: LangGraph SqliteSaver database.
        thread_id: LangGraph thread id of the student (ADR-008).
        log_level: logging level for the application.
    """

    data_dir: Path = PROJECT_ROOT / "data"
    prompts_dir: Path = PROJECT_ROOT / "prompts"
    training_state_path: Path = PROJECT_ROOT / "data" / "training-state.json"
    checkpoint_path: Path = PROJECT_ROOT / "data" / "checkpoints.sqlite"
    thread_id: str = "student:alex"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


# Module-level singletons (rag_GigaChat convention)
gigachat_config = GigaChatConfig()
tavily_config = TavilyConfig()
trainer_config = TrainerConfig()
