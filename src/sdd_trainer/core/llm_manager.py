"""GigaChat client via the OpenAI-compatible cloud.ru API (criterion 1).

Wraps ``openai.OpenAI`` with ``base_url`` from :class:`~sdd_trainer.config.GigaChatConfig`
(ADR-005, AIA_01 course pattern):

- ``chat()`` — dialogue completions with streaming support;
- ``llm_call(structure=PydanticModel)`` — structured output via ``tools`` +
  ``tool_choice`` (AIA_02 pattern), used for quiz grading and routing;
- model fallback: ``GigaChat/GigaChat-3-Pro`` -> ``GigaChat/GigaChat-3.5-Reasoning``
  (exact fallback ID to be confirmed via ``models.list`` in phase 1).

Phase 0: stub only — no API calls, no network imports. Implemented by the
``add-console-trainer`` change (phase 1).
"""
from __future__ import annotations

from typing import Optional, Type, TypeVar

from sdd_trainer.config import GigaChatConfig

T = TypeVar("T")


class LLMManager:
    """Thin client over the OpenAI-compatible GigaChat API (ADR-005)."""

    def __init__(self, config: Optional[GigaChatConfig] = None) -> None:
        """Store the config; the ``openai`` client is created in phase 1."""
        self.config = config or GigaChatConfig()

    def chat(self, messages: list[dict], stream: bool = False) -> str:
        """Run a dialogue completion (implemented in phase 1)."""
        pass

    def llm_call(self, messages: list[dict], structure: Type[T]) -> T:
        """Run a completion with structured output (implemented in phase 1)."""
        pass
