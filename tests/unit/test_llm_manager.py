"""Unit tests for the GigaChat client seam (no network, ADR-005 / T1+T2)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from openai import OpenAIError

from sdd_trainer.config import GigaChatConfig
from sdd_trainer.core.llm_manager import LLMManager, StructuredOutputError
from sdd_trainer.models import Assessment

pytestmark = pytest.mark.unit

FALLBACK_MODEL = "ai-sage/GigaChat3.5-432B-A28B-Reasoning"


def _response(text: str) -> SimpleNamespace:
    """Build a minimal openai-like chat completion response."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _tool_call_response(tool_name: str, arguments: str) -> SimpleNamespace:
    """Build an openai-like completion whose message carries one tool call."""
    function = SimpleNamespace(name=tool_name, arguments=arguments)
    tool_call = SimpleNamespace(id="call_1", type="function", function=function)
    message = SimpleNamespace(content=None, tool_calls=[tool_call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _assessment_payload(**overrides) -> str:
    """Valid Assessment tool-call arguments as a JSON string."""
    payload = {
        "domain": "openspec-basics",
        "level": "partial",
        "justification": "Знает про specs/, но путается в change proposals.",
        "confidence": 0.6,
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


class FakeOpenAI:
    """Stand-in for ``openai.OpenAI`` recording ``create()`` calls (test seam).

    ``replies`` items may be a plain string (text completion), a prebuilt
    completion object (e.g. a tool-call response) or an exception instance
    to raise — simulating a model failure.
    """

    def __init__(self, replies: list) -> None:
        self._replies = list(replies)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model: str, messages: list[dict], **kwargs) -> SimpleNamespace:
        self.calls.append({"model": model, "messages": messages, **kwargs})
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, str):
            return _response(reply)
        return reply


def _manager(fake: FakeOpenAI) -> LLMManager:
    return LLMManager(config=GigaChatConfig(api_key="test"), client=fake)


class TestChat:
    """chat(): plain completion with an in-memory history (T1)."""

    def test_returns_reply_and_grows_history(self) -> None:
        fake = FakeOpenAI(replies=["Привет!", "Отлично!"])
        manager = _manager(fake)

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
        manager = _manager(fake)

        manager.chat("hi")

        assert fake.calls[0]["messages"] == [{"role": "user", "content": "hi"}]


class TestLLMCall:
    """llm_call(): structured output via tools + tool_choice (ADR-005, AIA_02)."""

    def test_parses_forced_tool_call_into_schema(self) -> None:
        fake = FakeOpenAI(
            replies=[_tool_call_response("Assessment", _assessment_payload())]
        )

        assessment = _manager(fake).llm_call(
            [{"role": "user", "content": "ответ"}], Assessment
        )

        assert isinstance(assessment, Assessment)
        assert assessment.level == "partial"
        assert assessment.domain == "openspec-basics"
        assert assessment.confidence == 0.6

    def test_sends_schema_tool_and_forced_tool_choice(self) -> None:
        fake = FakeOpenAI(
            replies=[_tool_call_response("Assessment", _assessment_payload())]
        )
        messages = [{"role": "user", "content": "ответ"}]

        _manager(fake).llm_call(messages, Assessment)

        call = fake.calls[0]
        assert call["model"] == "GigaChat/GigaChat-3-Pro"
        assert call["messages"] == messages
        assert len(call["tools"]) == 1
        function = call["tools"][0]["function"]
        assert function["name"] == "Assessment"
        assert function["parameters"] == Assessment.model_json_schema()
        assert call["tool_choice"] == {
            "type": "function",
            "function": {"name": "Assessment"},
        }

    def test_tool_description_comes_from_schema(self) -> None:
        fake = FakeOpenAI(
            replies=[_tool_call_response("Assessment", _assessment_payload())]
        )

        _manager(fake).llm_call([{"role": "user", "content": "ответ"}], Assessment)

        function = fake.calls[0]["tools"][0]["function"]
        assert function["description"] == Assessment.model_json_schema()["description"]

    def test_no_tool_call_raises_instead_of_text_parsing(self) -> None:
        fake = FakeOpenAI(replies=["уровень: partial, но без структуры"])

        with pytest.raises(StructuredOutputError):
            _manager(fake).llm_call(
                [{"role": "user", "content": "ответ"}], Assessment
            )

    def test_invalid_arguments_raise(self) -> None:
        fake = FakeOpenAI(
            replies=[
                _tool_call_response("Assessment", _assessment_payload(level="guru"))
            ]
        )

        with pytest.raises(StructuredOutputError):
            _manager(fake).llm_call(
                [{"role": "user", "content": "ответ"}], Assessment
            )

    def test_broken_json_raises(self) -> None:
        fake = FakeOpenAI(replies=[_tool_call_response("Assessment", "не json")])

        with pytest.raises(StructuredOutputError):
            _manager(fake).llm_call(
                [{"role": "user", "content": "ответ"}], Assessment
            )

    def test_history_untouched(self) -> None:
        fake = FakeOpenAI(
            replies=[_tool_call_response("Assessment", _assessment_payload())]
        )
        manager = _manager(fake)

        manager.llm_call([{"role": "user", "content": "ответ"}], Assessment)

        assert manager.history == []


class TestComplete:
    """complete(): plain text completion for the teach node (T4, task 3.3)."""

    def test_returns_text_without_tools_and_without_history(self) -> None:
        fake = FakeOpenAI(replies=["Текст урока."])
        manager = _manager(fake)
        messages = [
            {"role": "system", "content": "Ты — тренер."},
            {"role": "user", "content": "скелет урока"},
        ]

        reply = manager.complete(messages)

        assert reply == "Текст урока."
        (call,) = fake.calls
        assert call["model"] == "GigaChat/GigaChat-3-Pro"
        assert call["messages"] == messages
        assert "tools" not in call  # prose, not a structured decision
        assert "tool_choice" not in call
        assert manager.history == []  # graph nodes own their state

    def test_empty_content_comes_back_as_empty_string(self) -> None:
        fake = FakeOpenAI(replies=[""])

        assert _manager(fake).complete([{"role": "user", "content": "x"}]) == ""

    def test_falls_back_to_reasoning_model(self) -> None:
        fake = FakeOpenAI(replies=[OpenAIError("primary down"), "Fallback-урок."])

        reply = _manager(fake).complete([{"role": "user", "content": "скелет"}])

        assert reply == "Fallback-урок."
        assert [call["model"] for call in fake.calls] == [
            "GigaChat/GigaChat-3-Pro",
            FALLBACK_MODEL,
        ]


class TestFallback:
    """Task 1.3: the reasoning model answers when the primary one fails."""

    def test_chat_falls_back_with_same_payload(self) -> None:
        fake = FakeOpenAI(replies=[OpenAIError("primary down"), "Ответ fallback."])

        reply = _manager(fake).chat("привет")

        assert reply == "Ответ fallback."
        assert [call["model"] for call in fake.calls] == [
            "GigaChat/GigaChat-3-Pro",
            FALLBACK_MODEL,
        ]
        assert fake.calls[0]["messages"] == fake.calls[1]["messages"]

    def test_llm_call_falls_back_with_tools(self) -> None:
        fake = FakeOpenAI(
            replies=[
                OpenAIError("primary down"),
                _tool_call_response(
                    "Assessment", _assessment_payload(level="knows_it")
                ),
            ]
        )

        assessment = _manager(fake).llm_call(
            [{"role": "user", "content": "ответ"}], Assessment
        )

        assert assessment.level == "knows_it"
        fallback_call = fake.calls[1]
        assert fallback_call["model"] == FALLBACK_MODEL
        assert fallback_call["tool_choice"]["function"]["name"] == "Assessment"
        assert "tools" in fallback_call

    def test_error_propagates_when_fallback_fails_too(self) -> None:
        fake = FakeOpenAI(
            replies=[OpenAIError("primary down"), OpenAIError("fallback down")]
        )

        with pytest.raises(OpenAIError):
            _manager(fake).chat("привет")

        assert len(fake.calls) == 2
