"""Integration tests: real GigaChat through the cloud.ru API (ADR-005, T2).

These tests hit the live endpoint and are skipped unless ``GIGACHAT_KEY`` is
set (locally the git-ignored ``.env`` provides it; CI without the secret
skips). The seam is the same as in the unit tests — ``LLMManager`` — but
wired to the real client (design.md).
"""
from __future__ import annotations

import os

import pytest

from sdd_trainer.__main__ import build_assessment_messages
from sdd_trainer.config import GigaChatConfig
from sdd_trainer.core.llm_manager import LLMManager
from sdd_trainer.models import Assessment

pytestmark = pytest.mark.integration

requires_key = pytest.mark.skipif(
    not os.getenv("GIGACHAT_KEY"),
    reason="GIGACHAT_KEY not set — live GigaChat tests skipped (see .env.example)",
)

KNOWLEDGEABLE_ANSWER = (
    "OpenSpec — инструмент spec-driven development. В specs/ лежат стабильные "
    "спецификации требований (source of truth), в changes/ — change proposals: "
    "предложения изменений с proposal.md, design.md, tasks.md и дельтой спеки. "
    "Proposal проходит review, применяется и архивируется, а спецификация "
    "остаётся источником истины."
)

NEWCOMER_ANSWER = "Честно говоря, впервые слышу про OpenSpec и не знаю, что это такое."


@requires_key
def test_assessment_structured_output_live() -> None:
    """WHEN a knowledgeable answer is assessed THEN the live API returns a valid Assessment."""
    manager = LLMManager(config=GigaChatConfig())

    assessment = manager.llm_call(
        build_assessment_messages(KNOWLEDGEABLE_ANSWER), Assessment
    )

    assert isinstance(assessment, Assessment)
    assert assessment.level in {"new_topic", "partial", "knows_it"}
    assert assessment.justification.strip()
    assert 0.0 <= assessment.confidence <= 1.0


@requires_key
def test_assessment_newcomer_is_new_topic_live() -> None:
    """WHEN the student has never heard of the topic THEN the level is new_topic."""
    manager = LLMManager(config=GigaChatConfig())

    assessment = manager.llm_call(
        build_assessment_messages(NEWCOMER_ANSWER), Assessment
    )

    assert assessment.level == "new_topic"


@requires_key
def test_fallback_to_reasoning_model_live() -> None:
    """Task 1.3 live: a broken primary model falls back to the reasoning model."""
    config = GigaChatConfig(model="GigaChat/no-such-model-for-fallback-smoke")
    manager = LLMManager(config=config)

    assessment = manager.llm_call(
        build_assessment_messages(NEWCOMER_ANSWER), Assessment
    )

    assert isinstance(assessment, Assessment)
    assert assessment.level == "new_topic"
