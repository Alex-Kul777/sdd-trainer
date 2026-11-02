"""Pydantic schemas for SDD Trainer (AIA_02 pattern).

These models define the structured state of the trainer: student profile,
level assessment, routing decisions, lesson plans, and quiz results. They
are used for structured LLM output (the ``llm_call(structure=...)`` pattern
via tools + tool_choice, ADR-005) and for persisting
``data/training-state.json``.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DomainProgress(BaseModel):
    """Student progress in a single SDD lesson domain."""

    domain: str
    score: float = 0.0
    streak: int = 0
    completed_lessons: int = 0


class UserProfile(BaseModel):
    """Student profile: progress across the 6 SDD domains."""

    student_id: str
    domains: dict[str, DomainProgress] = Field(default_factory=dict)


class Assessment(BaseModel):
    """Structured assessment of the student's level in a lesson domain.

    Produced from the calibration answer via
    ``llm_call(messages, structure=Assessment)`` — tools + tool_choice, no
    free-text parsing (ADR-005, issue #3 / task 2.1). The ``level``
    vocabulary matches the routing paths of the spec: ``new_topic`` — the
    topic is unfamiliar, ``partial`` — understanding with gaps,
    ``knows_it`` — solid command. A low ``confidence`` is the signal for the
    ``clarification`` path; the routing logic itself is ticket T3.
    """

    domain: str = Field(
        description="Домен урока, к которому относится оценка (например: openspec-basics)",
    )
    level: Literal["new_topic", "partial", "knows_it"] = Field(
        description=(
            "Уровень ученика в домене: new_topic — тема совершенно незнакома; "
            "partial — частичное понимание, есть пробелы; knows_it — уверенное владение"
        ),
    )
    justification: str = Field(
        description=(
            "Краткое обоснование оценки: что именно в ответе ученика "
            "указывает на этот уровень (1–2 предложения)"
        ),
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description=(
            "Уверенность оценки от 0.0 до 1.0; низкое значение — "
            "сигнал задать уточняющий вопрос"
        ),
    )


class RouteDecision(BaseModel):
    """Structured routing decision: the lesson path chosen from an assessment.

    The paths are fixed by the spec (routing with at least three paths):
    ``knows_it`` / ``partial`` / ``new_topic`` plus ``clarification`` when
    the assessment is inconclusive. The routing node logic is ticket T3 —
    this schema only fixes the structured contract (task 2.1).
    """

    path: Literal["knows_it", "partial", "new_topic", "clarification"] = Field(
        description="Выбранный путь обучения: knows_it / partial / new_topic / clarification",
    )
    reason: str = Field(
        description="Краткая причина выбора пути — видна в логе сессии (spec: routing scenario)",
    )


class DocsDecision(BaseModel):
    """Structured decision: does the lesson need fresh external docs (T4).

    The teach node asks this before unfolding (task 3.3): when the lesson
    skeleton alone is not enough material, the node pulls fresh
    documentation through ``search_sdd_docs`` (Tavily, ADR-006) and feeds
    it into the unfolding prompt. The decision goes through the same
    structured-output seam as Assessment / RouteDecision (ADR-005).

    ``query`` is deliberately optional: live models occasionally ask for
    docs but omit the query (seen in the live demo 02.11) — the teach node
    then falls back to a deterministic domain default
    (``core.prompts.default_docs_query``) instead of failing the lesson.
    """

    needs_docs: bool = Field(
        description=(
            "true — материала скелета не хватает для полноценного урока, "
            "нужен свежий поиск документации"
        ),
    )
    query: str = Field(
        default="",
        description=(
            "Поисковый запрос на английском для search_sdd_docs — "
            "всегда заполняй его, когда needs_docs=true"
        ),
    )
    reason: str = Field(
        description="Краткое обоснование решения — попадает в лог сеанса",
    )


class QuizQuestion(BaseModel):
    """A single quiz question with a reference answer (reproducible F1, Q10)."""

    domain: str
    question: str
    reference_answer: str


class QuizResult(BaseModel):
    """Structured outcome of a knowledge check (structured output pattern)."""

    domain: str
    score: float
    passed: bool
    feedback: str = ""


class LessonPlan(BaseModel):
    """Lesson skeleton unfolded by GigaChat (hybrid authorship, Q10)."""

    domain: str
    title: str
    outline: list[str] = Field(default_factory=list)
    socratic_question: str = ""
