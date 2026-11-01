"""Pydantic schemas for SDD Trainer (AIA_02 pattern).

These models define the structured state of the trainer: student profile,
lesson plans, and quiz results. They are used for structured LLM output
(the ``llm_call(structure=...)`` pattern via tools + tool_choice) and for
persisting ``data/training-state.json``.
"""
from __future__ import annotations

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
