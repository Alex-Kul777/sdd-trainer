"""Unit tests for the graph prompt builders (pure functions, T3 + T4)."""
from __future__ import annotations

import pytest

from sdd_trainer.core.prompts import (
    ASSESSMENT_DOMAIN,
    CALIBRATION_QUESTION,
    DOCS_SYSTEM_PROMPT,
    ROUTE_SYSTEM_PROMPT,
    TEACH_SYSTEM_PROMPT,
    build_assessment_messages,
    build_clarifying_question,
    build_docs_decision_messages,
    build_reassessment_messages,
    build_route_messages,
    build_teach_messages,
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


SKELETON = (
    "# OpenSpec-основы\n\n## Goal\nЦель урока.\n\n## Key concepts\n- specs/\n"
    "- changes/\n\n## Socratic questions\n- Зачем спека?\n\n## Examples\n"
    "- SHALL/WHEN/THEN\n\n## Quiz ref\n- data/quizzes/openspec-basics.json\n"
)

SEARCH_RESULTS = [
    {
        "title": "OpenSpec — workflow",
        "url": "https://example.org/openspec-workflow",
        "content": "explore → propose → apply → archive",
    }
]


class TestDocsDecisionMessages:
    """build_docs_decision_messages: skeleton + level -> docs decision call."""

    def test_shape_and_content(self) -> None:
        messages = build_docs_decision_messages(
            SKELETON, "partial", "путается в changes/"
        )

        assert [message["role"] for message in messages] == ["system", "user"]
        assert messages[0]["content"] == DOCS_SYSTEM_PROMPT
        content = messages[1]["content"]
        assert "## Key concepts" in content  # the skeleton is embedded whole
        assert "partial" in content
        assert "путается в changes/" in content

    def test_docs_prompt_requires_the_docsdecision_call(self) -> None:
        assert "DocsDecision" in DOCS_SYSTEM_PROMPT


class TestTeachMessages:
    """build_teach_messages: skeleton unfolded per level (task 3.3, ADR-009)."""

    def test_contains_skeleton_and_new_topic_directive(self) -> None:
        messages = build_teach_messages(SKELETON, "new_topic", "", [])

        assert messages[0]["content"] == TEACH_SYSTEM_PROMPT
        content = messages[1]["content"]
        assert "## Key concepts" in content  # the skeleton is embedded whole
        assert "с нуля" in content  # new_topic: full lesson from scratch

    def test_partial_directive_targets_the_gaps(self) -> None:
        content = build_teach_messages(
            SKELETON, "partial", "путается в changes/", []
        )[1]["content"]

        assert "пробел" in content
        assert "путается в changes/" in content

    def test_knows_it_directive_is_a_recap(self) -> None:
        content = build_teach_messages(SKELETON, "knows_it", "", [])[1]["content"]

        assert "рекап" in content

    def test_levels_produce_distinct_directives(self) -> None:
        contents = {
            level: build_teach_messages(SKELETON, level, "", [])[1]["content"]
            for level in ("new_topic", "partial", "knows_it")
        }

        assert len(set(contents.values())) == 3

    def test_search_results_block_present_when_results_given(self) -> None:
        content = build_teach_messages(
            SKELETON, "new_topic", "", SEARCH_RESULTS
        )[1]["content"]

        assert "search_sdd_docs" in content
        assert "https://example.org/openspec-workflow" in content
        assert "OpenSpec — workflow" in content
        assert "explore → propose → apply → archive" in content

    def test_no_search_block_without_results(self) -> None:
        content = build_teach_messages(SKELETON, "new_topic", "", [])[1]["content"]

        assert "search_sdd_docs" not in content

    def test_teach_system_prompt_names_all_three_levels(self) -> None:
        for level in ("new_topic", "partial", "knows_it"):
            assert level in TEACH_SYSTEM_PROMPT


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
