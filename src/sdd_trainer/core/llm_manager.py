"""GigaChat client via the OpenAI-compatible cloud.ru API (criterion 1).

Wraps ``openai.OpenAI`` with ``base_url`` from
:class:`~sdd_trainer.config.GigaChatConfig` (ADR-005, AIA_01 course pattern):

- ``chat()`` — plain dialogue completions with an in-memory history (T1);
- ``llm_call(structure=PydanticModel)`` — structured output via ``tools`` +
  ``tool_choice`` (AIA_02 pattern) — follow-up ticket T2 (task 1.2);
- fallback to the reasoning model (task 1.3) — follow-up ticket.

The ``openai`` client is created lazily: importing this module never touches
the network. Unit tests inject a fake client through the ``client`` parameter
(the test seam, design.md).
"""
from __future__ import annotations

from typing import Optional, Type, TypeVar

from openai import OpenAI

from sdd_trainer.config import GigaChatConfig

T = TypeVar("T")


class LLMManager:
    """Thin client over the OpenAI-compatible GigaChat API (ADR-005)."""

    def __init__(
        self,
        config: Optional[GigaChatConfig] = None,
        system_prompt: Optional[str] = None,
        client: Optional[OpenAI] = None,
    ) -> None:
        """Store the config, system prompt and an optional injected client.

        Args:
            config: GigaChat access settings; defaults to ``GigaChatConfig()``.
            system_prompt: optional system message prepended to every call.
            client: test seam — unit tests inject a fake ``OpenAI`` client
                instead of the real one (no network).
        """
        self.config = config or GigaChatConfig()
        self.system_prompt = system_prompt
        self.history: list[dict] = []
        self._client = client

    @property
    def client(self) -> OpenAI:
        """Lazily create the OpenAI client bound to the cloud.ru endpoint."""
        if self._client is None:
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
            )
        return self._client

    def chat(self, user_message: str) -> str:
        """Send one user message (with the in-memory history), return the reply.

        Builds ``[system?] + history + [user]``, runs a plain chat completion
        (no structured output — that is T2), appends both turns to the
        history and returns the assistant text.
        """
        messages: list[dict] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_message})

        completion = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
        )
        reply = completion.choices[0].message.content or ""

        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def llm_call(self, messages: list[dict], structure: Type[T]) -> T:
        """Run a completion with structured output (T2, task 1.2 — not yet)."""
        raise NotImplementedError(
            "Structured output via tools + tool_choice arrives in T2 (task 1.2)"
        )
