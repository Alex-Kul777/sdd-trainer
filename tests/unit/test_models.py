"""Unit tests for the Pydantic schemas (AIA_02): Assessment + RouteDecision."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdd_trainer.models import Assessment, RouteDecision

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
