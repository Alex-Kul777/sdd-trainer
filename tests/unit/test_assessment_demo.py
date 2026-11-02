"""Unit tests for the ``--assess`` demo glue (pure helpers in __main__, T2)."""
from __future__ import annotations

import pytest

from sdd_trainer.__main__ import (
    ASSESSMENT_DOMAIN,
    ASSESSMENT_SYSTEM_PROMPT,
    CALIBRATION_QUESTION,
    build_assessment_messages,
)

pytestmark = pytest.mark.unit


class TestBuildAssessmentMessages:
    """The assessment prompt: system + one user message (question + answer)."""

    def test_shape_and_content(self) -> None:
        messages = build_assessment_messages("Я знаю OpenSpec: specs и changes.")

        assert [message["role"] for message in messages] == ["system", "user"]
        assert messages[0]["content"] == ASSESSMENT_SYSTEM_PROMPT
        assert CALIBRATION_QUESTION in messages[1]["content"]
        assert "Я знаю OpenSpec: specs и changes." in messages[1]["content"]


class TestAssessmentPrompts:
    """The prompts name the domain and the fixed level vocabulary."""

    def test_system_prompt_names_domain_and_levels(self) -> None:
        assert ASSESSMENT_DOMAIN == "openspec-basics"
        assert "openspec-basics" in ASSESSMENT_SYSTEM_PROMPT
        for level in ("new_topic", "partial", "knows_it"):
            assert level in ASSESSMENT_SYSTEM_PROMPT

    def test_calibration_question_is_openspec_basics(self) -> None:
        assert "OpenSpec" in CALIBRATION_QUESTION
        assert "specs/" in CALIBRATION_QUESTION
        assert "changes/" in CALIBRATION_QUESTION
