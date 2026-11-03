"""Deterministic quiz scoring: token F1 against reference answers (T5).

ADR-009 / grilling Q10: reference answers live in the authored quiz JSON,
so the score is reproducible — no LLM judge. The metric is the SQuAD-style
token-overlap F1: normalize to lowercase word tokens (Cyrillic + Latin +
digits, punctuation dropped), count the multiset intersection, and take
the harmonic mean of precision and recall. Per-question F1s aggregate into
a weighted score (authored weights), compared against the quiz's pass
threshold. Task 3.4 / 4.2 wiring lives in the graph quiz node; this module
is pure computation with no I/O and no LLM.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import NamedTuple

from sdd_trainer.models import Quiz, QuizResult

#: Word tokens: Latin + Cyrillic (with ё) + digits. Punctuation and
#: whitespace are separators — "SHALL," and "shall" are the same token.
_TOKEN_RE = re.compile(r"[a-zа-яё0-9]+")


def tokenize(text: str) -> list[str]:
    """Split text into lowercase word tokens (punctuation dropped)."""
    return _TOKEN_RE.findall(text.lower())


def answer_f1(answer: str, reference: str) -> float:
    """Reproducible token-overlap F1 of an answer against its reference.

    SQuAD convention: both token bags empty -> 1.0 (identical), exactly
    one empty -> 0.0. Otherwise precision = |intersection| / |answer
    tokens|, recall = |intersection| / |reference tokens|, F1 is their
    harmonic mean; repeated tokens count as a multiset.
    """
    answer_tokens = tokenize(answer)
    reference_tokens = tokenize(reference)
    if not answer_tokens and not reference_tokens:
        return 1.0
    if not answer_tokens or not reference_tokens:
        return 0.0
    overlap = sum((Counter(answer_tokens) & Counter(reference_tokens)).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(answer_tokens)
    recall = overlap / len(reference_tokens)
    return 2 * precision * recall / (precision + recall)


class QuizOutcome(NamedTuple):
    """Scored quiz: the structured result + per-question F1s for the log."""

    result: QuizResult
    question_f1s: list[float]


def score_quiz(quiz: Quiz, answers: list[str]) -> QuizOutcome:
    """Score a completed quiz: weighted F1 aggregate + pass verdict.

    Args:
        quiz: the authored domain quiz (reference answers, weights,
            pass threshold — ADR-009).
        answers: the student's answers, one per question, in order.

    Returns:
        A :class:`QuizOutcome`: the ``QuizResult`` (domain, weighted score,
        passed, deterministic feedback with per-question F1s) and the raw
        per-question F1 values (for the session log).

    Raises:
        ValueError: the number of answers does not match the number of
            questions — a half-answered quiz must fail loudly instead of
            being scored against the wrong references.
    """
    if len(answers) != len(quiz.questions):
        raise ValueError(
            f"квиз {quiz.domain}: получено {len(answers)} ответ(ов) на "
            f"{len(quiz.questions)} вопрос(ов) — количество должно совпадать"
        )

    f1s = [
        answer_f1(answer, question.reference_answer)
        for question, answer in zip(quiz.questions, answers)
    ]
    total_weight = sum(question.weight for question in quiz.questions)
    score = sum(
        question.weight * f1 for question, f1 in zip(quiz.questions, f1s)
    ) / total_weight
    passed = score >= quiz.pass_threshold

    per_question = ", ".join(
        "{}={:.2f}".format(question.id or f"вопрос {index + 1}", f1)
        for index, (question, f1) in enumerate(zip(quiz.questions, f1s))
    )
    feedback = (
        "F1 по вопросам: {}. Итог: {:.2f} — {} (порог {:.2f})".format(
            per_question,
            score,
            "зачёт" if passed else "не зачёт",
            quiz.pass_threshold,
        )
    )
    result = QuizResult(
        domain=quiz.domain,
        score=score,
        passed=passed,
        feedback=feedback,
    )
    return QuizOutcome(result=result, question_f1s=f1s)
