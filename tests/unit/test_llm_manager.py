"""Unit tests for the GigaChat client seam (no network, ADR-005 / T1)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from sdd_trainer.config import GigaChatConfig
from sdd_trainer.core.llm_manager import LLMManager

pytestmark = pytest.mark.unit


def _response(text: str) -> SimpleNamespace:
    """Build a minimal openai-like chat completion response."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


class FakeOpenAI:
    """Stand-in for ``openai.OpenAI`` recording ``create()`` calls (test seam)."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model: str, messages: list[dict]) -> SimpleNamespace:
        self.calls.append({"model": model, "messages": messages})
        return _response(self._replies.pop(0))


class TestChat:
    """chat(): plain completion with an in-memory history (T1)."""

    def test_returns_reply_and_grows_history(self) -> None:
        fake = FakeOpenAI(replies=["Привет!", "Отлично!"])
        manager = LLMManager(config=GigaChatConfig(api_key="test"), client=fake)

        assert manager.chat("привет") == "Привет!"
        assert manager.history == [
            {"role": "user", "content": "привет"},
            {"role": "assistant", "content": "Привет!"},
        ]
        assert manager.chat("как дела?") == "Отлично!"
        assert len(manager.history) == 4

    def test_sends_system_prompt_history_and_new_turn(self) -> None:
        fake = FakeOpenAI(replies=["Раз.", "Два."])
        manager = LLMManager(
            config=GigaChatConfig(api_key="test"),
            system_prompt="Ты — тренер.",
            client=fake,
        )
        manager.chat("вопрос 1")
        manager.chat("вопрос 2")

        last = fake.calls[-1]
        assert last["model"] == "GigaChat/GigaChat-3-Pro"
        assert last["messages"] == [
            {"role": "system", "content": "Ты — тренер."},
            {"role": "user", "content": "вопрос 1"},
            {"role": "assistant", "content": "Раз."},
            {"role": "user", "content": "вопрос 2"},
        ]

    def test_no_system_prompt_when_unset(self) -> None:
        fake = FakeOpenAI(replies=["ok"])
        manager = LLMManager(config=GigaChatConfig(api_key="test"), client=fake)

        manager.chat("hi")

        assert fake.calls[0]["messages"] == [{"role": "user", "content": "hi"}]


class TestLLMCall:
    """llm_call(): structured output is T2 — honest NotImplementedError."""

    def test_not_implemented_in_t1(self) -> None:
        manager = LLMManager(config=GigaChatConfig(api_key="test"))
        with pytest.raises(NotImplementedError):
            manager.llm_call(messages=[], structure=dict)
