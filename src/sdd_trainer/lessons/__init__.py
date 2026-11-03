"""Lesson content for the 6 SDD domains — the trainer's curriculum.

Domains (PLAN-FINAL-PROJECT.md, section 2):

1. ``sdd-fundamentals`` — spec as the source of truth, plan before code;
2. ``openspec-structure`` — specs/ vs changes/;
3. ``requirement-writing`` — SHALL requirements + WHEN/THEN scenarios;
4. ``change-proposals`` — proposal -> design -> tasks;
5. ``openspec-workflow`` — explore -> propose -> apply -> archive;
6. ``brownfield-sdd`` — incremental changes in a live project.

Lesson skeletons (few-shot prompts) live in ``prompts/lessons/<domain>.md``
with fixed ADR-009 sections; quizzes with reference answers live in
``data/quizzes/<domain>.json`` (hybrid authorship, grilling Q10). The loader
below enforces the fixed-sections contract of ADR-009 — a skeleton without
every section is a content bug and fails loudly. The first content slice —
``openspec-basics`` — landed in T4 (issue #5, task 5.1).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from sdd_trainer.config import trainer_config
from sdd_trainer.models import Quiz

LESSON_DOMAINS: list[str] = [
    "sdd-fundamentals",
    "openspec-structure",
    "requirement-writing",
    "change-proposals",
    "openspec-workflow",
    "brownfield-sdd",
]

#: Fixed skeleton sections — the stable unfolding contract (ADR-009):
#: every ``prompts/lessons/<domain>.md`` must carry them as ``## <section>``
#: lines, in this order.
LESSON_SECTIONS: tuple[str, ...] = (
    "Goal",
    "Key concepts",
    "Socratic questions",
    "Examples",
    "Quiz ref",
)


def lesson_skeleton_path(
    domain: str, prompts_dir: Optional[Path] = None
) -> Path:
    """Return the ADR-009 location of a lesson skeleton.

    ``<prompts_dir>/lessons/<domain>.md`` — by default the repo ``prompts/``
    directory (``TrainerConfig.prompts_dir``).
    """
    base = Path(prompts_dir) if prompts_dir is not None else trainer_config.prompts_dir
    return base / "lessons" / f"{domain}.md"


def missing_skeleton_sections(markdown: str) -> list[str]:
    """Return the ADR-009 sections absent from a skeleton markdown.

    A section counts only as an exact ``## <section>`` line, so a ``###``
    subheader or a ``## Goals`` typo does not satisfy the contract.
    """
    lines = {line.strip() for line in markdown.splitlines()}
    return [
        section for section in LESSON_SECTIONS if f"## {section}" not in lines
    ]


def load_lesson_skeleton(
    domain: str, prompts_dir: Optional[Path] = None
) -> str:
    """Read the lesson skeleton of a domain and validate its sections.

    Args:
        domain: lesson domain id, e.g. ``openspec-basics``.
        prompts_dir: directory holding ``lessons/<domain>.md``; defaults to
            the repo ``prompts/`` directory.

    Returns:
        The skeleton markdown text.

    Raises:
        FileNotFoundError: no skeleton file exists for the domain.
        ValueError: the skeleton is missing one or more ADR-009 sections —
            the fixed sections are the unfolding contract, so a broken
            skeleton must fail loudly instead of degrading the lesson.
    """
    path = lesson_skeleton_path(domain, prompts_dir=prompts_dir)
    markdown = path.read_text(encoding="utf-8")
    missing = missing_skeleton_sections(markdown)
    if missing:
        raise ValueError(
            f"скелет урока {path} не содержит секции ADR-009: "
            + ", ".join(missing)
        )
    return markdown


def quiz_path(domain: str, data_dir: Optional[Path] = None) -> Path:
    """Return the ADR-009 location of a domain quiz.

    ``<data_dir>/quizzes/<domain>.json`` — by default the repo ``data/``
    directory (``TrainerConfig.data_dir``).
    """
    base = Path(data_dir) if data_dir is not None else trainer_config.data_dir
    return base / "quizzes" / f"{domain}.json"


def load_quiz(domain: str, data_dir: Optional[Path] = None) -> Quiz:
    """Read and validate the domain quiz (ADR-009, task 5.2).

    The JSON is validated through the ``Quiz`` schema (Pydantic — loud
    failure on a broken quiz: missing reference answers, non-positive
    weights, no questions), and the quiz's own ``domain`` field must match
    the requested one — a mismatched file is a content bug.

    Args:
        domain: quiz domain id, e.g. ``openspec-basics``.
        data_dir: directory holding ``quizzes/<domain>.json``; defaults to
            the repo ``data/`` directory.

    Returns:
        The validated :class:`sdd_trainer.models.Quiz`.

    Raises:
        FileNotFoundError: no quiz file exists for the domain.
        ValueError: the quiz declares a different domain, or has no
            questions.
        pydantic.ValidationError: the JSON violates the quiz contract
            (missing question / reference_answer, weight <= 0, threshold
            outside [0, 1]).
    """
    import json

    path = quiz_path(domain, data_dir=data_dir)
    quiz = Quiz.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )
    if quiz.domain != domain:
        raise ValueError(
            f"квиз {path} объявляет домен {quiz.domain!r}, а запрошен "
            f"{domain!r} — файл лежит не на своём месте"
        )
    return quiz
