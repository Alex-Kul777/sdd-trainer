"""Prompt builders for the trainer graph nodes (pure functions, unit-tested).

The assessment prompts were introduced in T2 (issue #3) inside ``__main__``;
T3 (issue #4) moves them here — next to the routing and clarification
prompts — so the graph nodes and the console share a single source.
``__main__`` re-exports the public names, so existing imports keep working.

All builders return plain OpenAI-style message dicts consumed by
``LLMManager.llm_call(messages, structure)`` (ADR-005: structured output via
tools + tool_choice — no free-text parsing).
"""
from __future__ import annotations

from sdd_trainer.models import Assessment

ASSESSMENT_DOMAIN = "openspec-basics"

CALIBRATION_QUESTION = (
    "Опиши своими словами, что такое OpenSpec: зачем в репозитории папки "
    "specs/ и changes/ и чем change proposal отличается от стабильной "
    "спецификации. Если тема незнакома — так и скажи, это нормально."
)

ASSESSMENT_SYSTEM_PROMPT = (
    "Ты — SDD Trainer, преподаватель Spec-Driven Development. Оцени уровень "
    "ученика в домене «OpenSpec-основы» (openspec-basics) по его ответу на "
    "калибровочный вопрос. Обязательно вызови функцию Assessment и заполни "
    "поля: level — new_topic (тема незнакома), partial (частичное понимание), "
    "knows_it (уверенное владение); justification — краткое обоснование "
    "(1–2 предложения); confidence — уверенность от 0.0 до 1.0; domain — "
    "openspec-basics. Оценивай честно: не завышай уровень и не льсти ученику."
)

ROUTE_SYSTEM_PROMPT = (
    "Ты — маршрутизатор SDD Trainer. По структуре Assessment ученика выбери "
    "ровно один путь обучения: knows_it — ученик уверенно знает тему, веди "
    "его сразу на квиз без лекции; partial — понимание с пробелами, нужен "
    "разбор; new_topic — тема незнакома, нужен полный урок с нуля. "
    "clarification — только если обоснование оценки противоречит уровню и "
    "выбрать путь невозможно. Обязательно вызови функцию RouteDecision: "
    "path — выбранный путь, reason — краткая причина выбора (она попадает "
    "в лог сеанса). Путь должен соответствовать уровню из Assessment."
)


def build_assessment_messages(student_answer: str) -> list[dict]:
    """Build the chat messages for the structured assessment call (T2).

    Pure function (unit-tested): the assessment system prompt plus one user
    message carrying the calibration question and the student's answer.
    Shared by the ``--assess`` demo, the assess graph node, and the live
    integration tests.
    """
    return [
        {"role": "system", "content": ASSESSMENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Калибровочный вопрос:\n{CALIBRATION_QUESTION}\n\n"
                f"Ответ ученика:\n{student_answer}"
            ),
        },
    ]


def build_route_messages(assessment: Assessment) -> list[dict]:
    """Build the chat messages for the structured routing call (T3, task 3.2).

    Pure function: the routing policy prompt plus the assessment as JSON.
    The route node calls this only when the assessment is confident enough
    (low-confidence assessments are routed to ``clarification``
    deterministically — see ``core.graph``).
    """
    return [
        {"role": "system", "content": ROUTE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Оценка ученика домена {assessment.domain} (Assessment, JSON):\n"
                f"{assessment.model_dump_json(indent=2, ensure_ascii=False)}\n\n"
                "Выбери путь обучения."
            ),
        },
    ]


def build_clarifying_question(assessment: Assessment) -> str:
    """Build the follow-up question for the clarification path (T3, task 3.2).

    The question shows the student why the assessment was inconclusive
    (the justification) and asks what exactly is familiar. Pure function.
    """
    return (
        f"Пока не берусь оценивать твой уровень уверенно: "
        f"{assessment.justification} "
        "Уточни, пожалуйста: что именно тебе уже знакомо в OpenSpec "
        "(specs/, changes/, change proposals), а что — впервые? "
        "Если не знаешь — так и скажи, это нормально."
    )


def build_reassessment_messages(
    calibration_answer: str,
    clarification_answers: list[str],
    previous: Assessment,
) -> list[dict]:
    """Build the messages for re-assessing after clarification answers.

    Pure function: the full dialogue so far (calibration question + answer,
    every clarification answer) plus the previous assessment as JSON, so the
    model can re-judge the level with the new evidence.
    """
    clarifications = "\n\n".join(
        f"Уточняющий ответ {number}: {answer}"
        for number, answer in enumerate(clarification_answers, start=1)
    )
    return [
        {"role": "system", "content": ASSESSMENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Калибровочный вопрос:\n{CALIBRATION_QUESTION}\n\n"
                f"Ответ ученика:\n{calibration_answer}\n\n"
                f"{clarifications}\n\n"
                f"Предыдущая оценка (Assessment, JSON):\n"
                f"{previous.model_dump_json(indent=2, ensure_ascii=False)}\n\n"
                "Переоцени уровень ученика с учётом уточнений."
            ),
        },
    ]
