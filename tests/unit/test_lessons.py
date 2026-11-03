"""Unit tests for the lesson skeleton loader (ADR-009, task 5.1, issue #5).

ADR-009 contract: skeletons are markdown files at ``prompts/lessons/<domain>.md``
with fixed sections — Goal / Key concepts / Socratic questions / Examples /
Quiz ref. The loader enforces that contract (a skeleton without the sections
is a content bug and must fail loudly), and the real ``openspec-basics``
skeleton — the phase 1 deliverable — is asserted against section names
written as literals here (independent source of truth, no tautology).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sdd_trainer.lessons import (
    lesson_skeleton_path,
    load_lesson_skeleton,
    load_quiz,
    missing_skeleton_sections,
    quiz_path,
)

pytestmark = pytest.mark.unit

#: ADR-009 section names — literals, deliberately not imported from the
#: package: the test is the independent check of the contract.
ADR009_SECTIONS = (
    "## Goal",
    "## Key concepts",
    "## Socratic questions",
    "## Examples",
    "## Quiz ref",
)


class TestSkeletonPath:
    """lesson_skeleton_path: ADR-009 location prompts/lessons/<domain>.md."""

    def test_path_is_prompts_lessons_domain_md(self) -> None:
        path = lesson_skeleton_path("openspec-basics", prompts_dir=Path("/x/p"))

        assert path == Path("/x/p/lessons/openspec-basics.md")

    def test_default_prompts_dir_is_the_repo_prompts_dir(self) -> None:
        from sdd_trainer.config import trainer_config

        path = lesson_skeleton_path("openspec-basics")

        assert path.parent.parent == trainer_config.prompts_dir


class TestOpenSpecBasicsSkeleton:
    """The phase 1 deliverable: prompts/lessons/openspec-basics.md (task 5.1)."""

    def test_skeleton_file_exists_and_loads(self) -> None:
        markdown = load_lesson_skeleton("openspec-basics")

        assert markdown.strip()
        assert markdown.startswith("# ")

    def test_skeleton_has_all_adr009_sections_as_exact_lines(self) -> None:
        lines = load_lesson_skeleton("openspec-basics").splitlines()

        for header in ADR009_SECTIONS:
            assert header in lines, f"секция ADR-009 отсутствует: {header}"

    def test_quiz_ref_points_at_the_domain_quiz(self) -> None:
        """The Quiz ref section cross-links the ADR-009 quiz of the domain."""
        markdown = load_lesson_skeleton("openspec-basics")

        assert "data/quizzes/openspec-basics.json" in markdown


class TestSkeletonValidation:
    """load_lesson_skeleton enforces the fixed-sections contract (ADR-009)."""

    @pytest.fixture
    def prompts_dir(self, tmp_path: Path) -> Path:
        lessons = tmp_path / "lessons"
        lessons.mkdir()
        return tmp_path

    def test_full_skeleton_passes(self, prompts_dir: Path) -> None:
        body = "\n".join(
            ["# Урок", *[f"{header}\nТекст секции." for header in ADR009_SECTIONS]]
        )
        (prompts_dir / "lessons" / "full.md").write_text(body, encoding="utf-8")

        assert load_lesson_skeleton("full", prompts_dir=prompts_dir) == body

    def test_missing_sections_are_named_in_the_error(self, prompts_dir: Path) -> None:
        (prompts_dir / "lessons" / "broken.md").write_text(
            "# Урок\n\n## Goal\nЦель.\n", encoding="utf-8"
        )

        with pytest.raises(ValueError) as excinfo:
            load_lesson_skeleton("broken", prompts_dir=prompts_dir)

        message = str(excinfo.value)
        assert "Key concepts" in message
        assert "Socratic questions" in message
        assert "Examples" in message
        assert "Quiz ref" in message
        assert "Goal" not in message.replace("Goal\n", "")  # present section not blamed

    def test_missing_skeleton_sections_helper(self) -> None:
        missing = missing_skeleton_sections("# Урок\n\n## Goal\nЦель.\n")

        assert missing == [
            "Key concepts",
            "Socratic questions",
            "Examples",
            "Quiz ref",
        ]

    def test_unknown_domain_raises_missing_file(self, prompts_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_lesson_skeleton("no-such-domain", prompts_dir=prompts_dir)


class TestQuizPath:
    """quiz_path: ADR-009 location data/quizzes/<domain>.json."""

    def test_path_is_data_quizzes_domain_json(self) -> None:
        path = quiz_path("openspec-basics", data_dir=Path("/x/data"))

        assert path == Path("/x/data/quizzes/openspec-basics.json")

    def test_default_data_dir_is_the_repo_data_dir(self) -> None:
        from sdd_trainer.config import trainer_config

        path = quiz_path("openspec-basics")

        assert path.parent.parent == trainer_config.data_dir


class TestOpenSpecBasicsQuiz:
    """The phase 1 deliverable: data/quizzes/openspec-basics.json (task 5.2)."""

    def test_quiz_file_exists_and_loads(self) -> None:
        quiz = load_quiz("openspec-basics")

        assert quiz.domain == "openspec-basics"
        assert len(quiz.questions) >= 3

    def test_every_question_has_reference_answer_and_weight(self) -> None:
        quiz = load_quiz("openspec-basics")

        for question in quiz.questions:
            assert question.question.strip()
            assert question.reference_answer.strip()
            assert question.weight > 0

    def test_weights_sum_is_independent_literal(self) -> None:
        """Weights are authored content: their sum is asserted as a literal
        computed by hand from the JSON, not via the loaded model."""
        quiz = load_quiz("openspec-basics")

        assert [q.weight for q in quiz.questions] == [1.0, 1.0, 1.0, 1.5, 1.0]

    def test_pass_threshold_is_within_unit_interval(self) -> None:
        quiz = load_quiz("openspec-basics")

        assert 0.0 < quiz.pass_threshold <= 1.0


class TestQuizValidation:
    """load_quiz enforces the ADR-009 quiz contract loudly."""

    @pytest.fixture
    def data_dir(self, tmp_path: Path) -> Path:
        quizzes = tmp_path / "quizzes"
        quizzes.mkdir()
        return tmp_path

    @staticmethod
    def _write(data_dir: Path, name: str, payload: object) -> None:
        import json

        (data_dir / "quizzes" / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def test_unknown_domain_raises_missing_file(self, data_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_quiz("no-such-domain", data_dir=data_dir)

    def test_domain_mismatch_raises_value_error(self, data_dir: Path) -> None:
        self._write(
            data_dir,
            "basics",
            {
                "domain": "other-domain",
                "pass_threshold": 0.6,
                "questions": [
                    {
                        "id": "q1",
                        "question": "В?",
                        "reference_answer": "Да",
                        "weight": 1.0,
                    }
                ],
            },
        )

        with pytest.raises(ValueError) as excinfo:
            load_quiz("basics", data_dir=data_dir)

        assert "other-domain" in str(excinfo.value)

    def test_empty_questions_raise_value_error(self, data_dir: Path) -> None:
        self._write(
            data_dir, "empty", {"domain": "empty", "questions": []}
        )

        with pytest.raises(ValueError):
            load_quiz("empty", data_dir=data_dir)

    def test_non_positive_weight_is_rejected(self, data_dir: Path) -> None:
        import pydantic

        self._write(
            data_dir,
            "badweight",
            {
                "domain": "badweight",
                "questions": [
                    {
                        "id": "q1",
                        "question": "В?",
                        "reference_answer": "Да",
                        "weight": 0,
                    }
                ],
            },
        )

        with pytest.raises(pydantic.ValidationError):
            load_quiz("badweight", data_dir=data_dir)
