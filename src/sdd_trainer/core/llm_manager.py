"""GigaChat client via the OpenAI-compatible cloud.ru API (criterion 1).

Wraps ``openai.OpenAI`` with ``base_url`` from
:class:`~sdd_trainer.config.GigaChatConfig` (ADR-005, AIA_01 course pattern):

- ``chat()`` — plain dialogue completions with an in-memory history (T1);
- ``llm_call(messages, structure)`` — structured output via ``tools`` +
  ``tool_choice`` (AIA_02 pattern): the Pydantic schema becomes a JSON-schema
  tool, the call is forced with ``tool_choice``, and the tool-call arguments
  are validated back into the schema. Free-text parsing is never attempted
  (ADR-005, issue #3 / task 1.2);
- fallback to the reasoning model when the primary one fails (task 1.3):
  every completion goes through :meth:`LLMManager._complete`, which retries
  the same request once with ``config.fallback_model``.

The ``openai`` client is created lazily: importing this module never touches
the network. Unit tests inject a fake client through the ``client`` parameter
(the test seam, design.md).
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Type, TypeVar

from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from sdd_trainer.config import GigaChatConfig

T = TypeVar("T")

logger = logging.getLogger(__name__)


class StructuredOutputError(RuntimeError):
    """A completion did not yield a parsable structured result.

    Raised when a response forced via ``tool_choice`` arrives without the
    expected tool call, or when the tool-call arguments fail validation
    against the requested Pydantic schema. Falling back to parsing the
    message text is deliberately not attempted (ADR-005).
    """


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
            system_prompt: optional system message prepended to every chat turn.
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
        (structured output is :meth:`llm_call`) with the primary model,
        falling back to the reasoning model on failure (task 1.3), appends
        both turns to the history and returns the assistant text.
        """
        messages: list[dict] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_message})

        completion = self._complete(messages=messages)
        reply = completion.choices[0].message.content or ""

        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def llm_call(self, messages: list[dict], structure: Type[T]) -> T:
        """Run a completion with structured output: tools + tool_choice (AIA_02).

        The Pydantic model is converted into a JSON-schema tool named after
        the schema class; ``tool_choice`` forces the model to call that tool;
        the tool-call arguments are validated back into ``structure``. The
        reply is never parsed as free text (ADR-005, task 1.2).

        Args:
            messages: chat messages for this call, used as-is. The in-memory
                :attr:`history` is not touched — graph nodes own their state.
            structure: the Pydantic model class to parse the result into.

        Returns:
            The validated instance of ``structure``.

        Raises:
            StructuredOutputError: the response carries no tool call, or its
                arguments do not validate against ``structure``.
            OpenAIError: both the primary and the fallback model failed.
        """
        tool = self._structure_tool(structure)
        completion = self._complete(
            messages=messages,
            tools=[tool],
            tool_choice={
                "type": "function",
                "function": {"name": tool["function"]["name"]},
            },
        )
        message = completion.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            raise StructuredOutputError(
                f"no tool call of {tool['function']['name']!r} in the response — "
                "free-text parsing is not attempted (ADR-005)"
            )
        arguments = tool_calls[0].function.arguments
        try:
            return structure.model_validate_json(arguments)
        except ValidationError as exc:
            raise StructuredOutputError(
                f"tool-call arguments do not validate against "
                f"{structure.__name__}: {exc}"
            ) from exc

    def _structure_tool(self, structure: Type[T]) -> dict[str, Any]:
        """Convert a Pydantic model into an OpenAI ``tools`` entry (AIA_02)."""
        schema = structure.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": structure.__name__,
                "description": schema.get("description")
                or f"Submit the structured {structure.__name__} result.",
                "parameters": schema,
            },
        }

    def _complete(self, **kwargs: Any) -> Any:
        """Create a completion; retry once with the reasoning model on failure.

        Task 1.3 (ADR-005): when the primary model raises, the very same
        request is re-sent with ``config.fallback_model``. If the fallback
        fails too, its error propagates to the caller. Only the exception
        type reaches the logs — error payloads never do.
        """
        try:
            return self.client.chat.completions.create(
                model=self.config.model, **kwargs
            )
        except OpenAIError as exc:
            logger.warning(
                "Primary model %s failed (%s); retrying with fallback model %s",
                self.config.model,
                type(exc).__name__,
                self.config.fallback_model,
            )
            return self.client.chat.completions.create(
                model=self.config.fallback_model, **kwargs
            )
