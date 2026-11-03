"""Unit tests for the deterministic quiz scoring (task 3.4, issue #6).

No LLM judge: the student's answers are scored by a reproducible token F1
against the authored reference answers (ADR-009). Every expected F1 value
below is computed by hand from the token bags — literals, deliberately not
recomputed with the same code the implementation uses (anti-tautology).
"""
from __future__ import annotations

import pytest

from sdd_trainer.core.quiz import answer_f1, score_quiz, tokenize
from sdd_trainer.models import Quiz, QuizQuestion

pytestmark = pytest.mark.unit


class TestTokenize:
    """tokenize: lowercase word tokens, punctuation dropped (SQuAD-style)."""

    def test_lowercases_and_splits_words(self) -> None:
        assert tokenize("Requirement, SHALL!") == ["requirement", "shall"]

    def test_keeps_cyrillic_and_digits(self) -> None:
        assert tokenize("Спека v2 — истина") == ["спека", "v2", "истина"]

    def test_empty_text_yields_no_tokens(self) -> None:
        assert tokenize("!!! ???") == []


class TestAnswerF1:
    """answer_f1: token-overlap F1, hand-computed literals."""

    def test_identical_answers_score_one(self) -> None:
        assert answer_f1(
            "спецификация источник истины", "спецификация источник истины"
        ) == 1.0

    def test_partial_overlap_is_two_thirds(self) -> None:
        # reference tokens: specs, стабильные, спецификации, changes,
        # предложения (5); answer tokens: specs, это, стабильные,
        # спецификации (4); overlap 3 -> P=3/4, R=3/5,
        # F1 = 2*(3/4)*(3/5)/((3/4)+(3/5)) = 2/3.
        assert answer_f1(
            "specs это стабильные спецификации",
            "specs стабильные спецификации changes предложения",
        ) == pytest.approx(2 / 3)

    def test_no_overlap_scores_zero(self) -> None:
        assert answer_f1("не знаю", "requirement shall инвариант") == 0.0

    def test_case_and_punctuation_do_not_matter(self) -> None:
        assert answer_f1("Requirement, SHALL!", "requirement shall") == 1.0

    def test_repeated_tokens_count_as_multiset(self) -> None:
        # ref: план, план, код; answer: план, код, код; overlap 2 ->
        # P=R=2/3 -> F1=2/3.
        assert answer_f1("план код код", "план план код") == pytest.approx(2 / 3)

    def test_empty_answer_against_reference_scores_zero(self) -> None:
        assert answer_f1("", "requirement shall") == 0.0

    def test_both_empty_score_one(self) -> None:
        assert answer_f1("", "") == 1.0


def _quiz() -> Quiz:
    """A two-question quiz with hand-checkable references and weights."""
    return Quiz(
        domain="openspec-basics",
        pass_threshold=0.6,
        questions=[
            QuizQuestion(
                id="q1",
                question="Формат требования?",
                reference_answer="requirement shall инвариант",
                weight=1.0,
            ),
            QuizQuestion(
                id="q2",
                question="Цикл работы?",
                reference_answer="explore propose apply archive",
                weight=3.0,
            ),
        ],
    )


class TestScoreQuiz:
    """score_quiz: weighted aggregate + pass verdict + per-question F1s."""

    def test_weighted_score_and_passed_verdict(self) -> None:
        # q1: answer [requirement, shall] vs ref of 3 tokens -> P=1, R=2/3
        # -> F1 = 4/5 = 0.80. q2: answer of 3 tokens vs ref of 4 -> P=1,
        # R=3/4 -> F1 = 6/7. Weighted: (1.0*4/5 + 3.0*6/7)/4.0 = 59/70.
        outcome = score_quiz(_quiz(), ["requirement shall", "explore propose apply"])

        assert outcome.result.domain == "openspec-basics"
        assert outcome.result.score == pytest.approx(59 / 70)
        assert outcome.result.passed is True
        assert outcome.question_f1s == [pytest.approx(4 / 5), pytest.approx(6 / 7)]

    def test_feedback_carries_per_question_f1_and_verdict(self) -> None:
        outcome = score_quiz(_quiz(), ["requirement shall", "explore propose apply"])

        feedback = outcome.result.feedback
        assert "q1" in feedback and "0.80" in feedback
        assert "q2" in feedback and "0.86" in feedback
        assert "0.84" in feedback  # 59/70 rounded to 2 decimals

    def test_below_threshold_fails(self) -> None:
        quiz = Quiz(
            domain="openspec-basics",
            pass_threshold=0.9,
            questions=[
                QuizQuestion(
                    id="q1",
                    question="Формат требования?",
                    reference_answer="requirement shall",
                    weight=1.0,
                )
            ],
        )
        # answer [requirement] vs ref [requirement, shall]: P=1, R=1/2,
        # F1 = 2/3 < 0.9.
        outcome = score_quiz(quiz, ["requirement"])

        assert outcome.result.score == pytest.approx(2 / 3)
        assert outcome.result.passed is False

    def test_answer_count_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            score_quiz(_quiz(), ["only one answer"])
