"""Unit tests for the graph prompt builders (pure functions, T3)."""
from __future__ import annotations

import pytest

from sdd_trainer.core.prompts import (
    ASSESSMENT_DOMAIN,
    CALIBRATION_QUESTION,
    ROUTE_SYSTEM_PROMPT,
    build_assessment_messages,
    build_clarifying_question,
    build_reassessment_messages,
    build_route_messages,
)
from sdd_trainer.models import Assessment

pytestmark = pytest.mark.unit


def _assessment(**overrides) -> Assessment:
    payload = {
        "domain": "openspec-basics",
        "level": "partial",
        "justification": "Знает про specs/, но путается в change proposals.",
        "confidence": 0.6,
    }
    payload.update(overrides)
    return Assessment.model_validate(payload)


class TestRouteMessages:
    """build_route_messages: policy prompt + assessment as JSON."""

    def test_shape_and_content(self) -> None:
        messages = build_route_messages(_assessment())

        assert [message["role"] for message in messages] == ["system", "user"]
        assert messages[0]["content"] == ROUTE_SYSTEM_PROMPT
        assert '"level": "partial"' in messages[1]["content"]
        assert "Выбери путь обучения." in messages[1]["content"]

    def test_policy_prompt_names_all_four_paths(self) -> None:
        for path in ("knows_it", "partial", "new_topic", "clarification"):
            assert path in ROUTE_SYSTEM_PROMPT


class TestClarifyingQuestion:
    """build_clarifying_question: shows the justification, asks what is familiar."""

    def test_question_carries_justification(self) -> None:
        question = build_clarifying_question(_assessment())

        assert "путается в change proposals" in question
        assert "Уточни" in question
        assert "OpenSpec" in question


class TestReassessmentMessages:
    """build_reassessment_messages: the whole dialogue + previous assessment."""

    def test_contains_all_answers_and_previous_assessment(self) -> None:
        messages = build_reassessment_messages(
            "калибровочный ответ",
            ["первое уточнение", "второе уточнение"],
            _assessment(confidence=0.2),
        )

        content = messages[1]["content"]
        assert [message["role"] for message in messages] == ["system", "user"]
        assert "калибровочный ответ" in content
        assert "первое уточнение" in content
        assert "второе уточнение" in content
        assert "Уточняющий ответ 1: первое уточнение" in content
        assert "Уточняющий ответ 2: второе уточнение" in content
        assert "Переоцени уровень ученика" in content
        assert '"confidence": 0.2' in content

    def test_assessment_messages_still_t2_shape(self) -> None:
        """The T2 builder keeps its contract after the move to core.prompts."""
        messages = build_assessment_messages("мой ответ")

        assert [message["role"] for message in messages] == ["system", "user"]
        assert CALIBRATION_QUESTION in messages[1]["content"]
        assert "мой ответ" in messages[1]["content"]
        assert ASSESSMENT_DOMAIN == "openspec-basics"
