"""Unit tests for the Pydantic schemas (AIA_02): Assessment + RouteDecision + DocsDecision."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdd_trainer.models import Assessment, DocsDecision, RouteDecision

pytestmark = pytest.mark.unit

VALID_ASSESSMENT = {
    "domain": "openspec-basics",
    "level": "partial",
    "justification": "Знает про specs/, путается в changes/.",
    "confidence": 0.6,
}


class TestAssessment:
    """Structured level assessment (issue #3): level + justification minimum."""

    def test_valid_payload(self) -> None:
        assessment = Assessment(**VALID_ASSESSMENT)

        assert assessment.level == "partial"
        assert assessment.domain == "openspec-basics"
        assert assessment.confidence == 0.6

    def test_confidence_has_default(self) -> None:
        payload = {k: v for k, v in VALID_ASSESSMENT.items() if k != "confidence"}

        assert Assessment(**payload).confidence == 0.8

    @pytest.mark.parametrize("level", ["new_topic", "partial", "knows_it"])
    def test_level_vocabulary_matches_routing_paths(self, level: str) -> None:
        assert Assessment(**{**VALID_ASSESSMENT, "level": level}).level == level

    def test_unknown_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Assessment(**{**VALID_ASSESSMENT, "level": "guru"})

    @pytest.mark.parametrize("confidence", [-0.1, 1.5])
    def test_confidence_bounds(self, confidence: float) -> None:
        with pytest.raises(ValidationError):
            Assessment(**{**VALID_ASSESSMENT, "confidence": confidence})

    def test_justification_required(self) -> None:
        payload = {k: v for k, v in VALID_ASSESSMENT.items() if k != "justification"}

        with pytest.raises(ValidationError):
            Assessment(**payload)


class TestDocsDecision:
    """Teach-node docs decision (T4, task 3.3): skeleton sufficiency."""

    def test_needs_docs_with_query(self) -> None:
        decision = DocsDecision(
            needs_docs=True,
            query="OpenSpec change proposal workflow",
            reason="В скелете нет свежих примеров workflow.",
        )

        assert decision.needs_docs is True
        assert decision.query == "OpenSpec change proposal workflow"

    def test_needs_docs_without_query_is_valid(self) -> None:
        """The query may be empty: live models omit fields (demo 02.11), and
        the teach node falls back to a domain default instead of dying."""
        decision = DocsDecision(
            needs_docs=True, query="", reason="Нужно больше примеров."
        )

        assert decision.needs_docs is True
        assert decision.query == ""

    def test_no_docs_allows_empty_query(self) -> None:
        decision = DocsDecision(
            needs_docs=False, query="", reason="Скелета достаточно."
        )

        assert decision.needs_docs is False

    def test_reason_required(self) -> None:
        with pytest.raises(ValidationError):
            DocsDecision(needs_docs=False)


class TestRouteDecision:
    """Routing contract fixed by the spec; the node logic is T3 (task 2.1)."""

    @pytest.mark.parametrize(
        "path", ["knows_it", "partial", "new_topic", "clarification"]
    )
    def test_paths_fixed_by_spec(self, path: str) -> None:
        decision = RouteDecision(path=path, reason="Оценка уверенная.")

        assert decision.path == path

    def test_unknown_path_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RouteDecision(path="advanced", reason="Нет такого пути в спеке.")

    def test_reason_required(self) -> None:
        with pytest.raises(ValidationError):
            RouteDecision(path="partial")
