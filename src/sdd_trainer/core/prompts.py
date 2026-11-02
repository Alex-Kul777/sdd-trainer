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

DOCS_SYSTEM_PROMPT = (
    "Ты — SDD Trainer. Реши, достаточно ли материала скелета урока, чтобы "
    "развернуть полноценный урок под уровень ученика, или нужно подтянуть "
    "свежую внешнюю документацию через поиск. Скелет компактен по замыслу: "
    "если для полного урока не хватает свежих примеров, практики или "
    "актуальных сведений об OpenSpec — запрашивай поиск. Обязательно вызови "
    "функцию DocsDecision и заполни все поля: needs_docs — true/false; "
    "query — поисковый запрос на английском для поиска документации — "
    "всегда заполняй его, когда needs_docs=true: без запроса поиск "
    "невозможен (пример: \"OpenSpec change proposal workflow\"); reason — "
    "краткое обоснование (оно попадёт в лог сеанса)."
)

#: Deterministic fallback search queries per domain. The teach node uses
#: them when the model asks for docs but omits the query — live models skip
#: fields occasionally (seen in the live demo 02.11), and the lesson must
#: not die on that: the intent (needs_docs) is the model's, the mechanics
#: (the query) can be derived.
DEFAULT_DOCS_QUERIES: dict[str, str] = {
    "openspec-basics": "OpenSpec spec-driven development",
}


def default_docs_query(domain: str) -> str:
    """Return the fallback search query for a domain (unknown -> generic).

    Pure function: the deterministic query the teach node searches with
    when the DocsDecision came back without one.
    """
    return DEFAULT_DOCS_QUERIES.get(
        domain, f"{domain} spec-driven development documentation"
    )

TEACH_SYSTEM_PROMPT = (
    "Ты — SDD Trainer, преподаватель Spec-Driven Development. Тебе дан "
    "скелет урока (markdown с фиксированными секциями Goal / Key concepts / "
    "Socratic questions / Examples / Quiz ref, ADR-009) и уровень ученика. "
    "Разверни скелет в полный урок на русском языке под этот уровень: "
    "new_topic — полный урок с нуля; partial — разбор пробелов; knows_it — "
    "краткий рекап. Сохраняй структуру секций скелета, пиши конкретно и "
    "живо, разбери примеры из скелета, в конце подведи итог и предложи "
    "проверить себя квизом. Не выдумывай факты, которых нет в скелете и в "
    "приложенной свежей документации; если чего-то не хватает — честно "
    "скажи об этом в уроке."
)

#: Per-level unfolding directives — the level reaches the teach node from
#: the assessment (``state["assessment"]["level"]``, T3 graph), and each
#: level gets a distinct unfolding strategy (task 3.3).
LEVEL_DIRECTIVES: dict[str, str] = {
    "new_topic": (
        "Уровень new_topic: тема ученику незнакома — построй полный урок "
        "с нуля: определи каждый термин, веди от простого к сложному, "
        "разбери каждый пример скелета подробно."
    ),
    "partial": (
        "Уровень partial: у ученика есть пробелы — не читай лекцию с нуля, "
        "сфокусируйся на пробелах из обоснования оценки и закрой их."
    ),
    "knows_it": (
        "Уровень knows_it: ученик уверенно владеет темой — дай краткий "
        "рекап ключевых инвариантов и подготовь к квизу."
    ),
}


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


def build_docs_decision_messages(
    skeleton: str, level: str, justification: str
) -> list[dict]:
    """Build the messages for the docs-sufficiency decision (T4, task 3.3).

    Pure function: the docs policy prompt plus the whole lesson skeleton,
    the student's level and the assessment justification. The teach node
    calls this before unfolding — when the skeleton alone is not enough,
    the node pulls fresh documentation via ``search_sdd_docs`` (ADR-006).
    """
    return [
        {"role": "system", "content": DOCS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Скелет урока (ADR-009):\n\n{skeleton}\n\n"
                f"Уровень ученика: {level}\n"
                f"Обоснование оценки: {justification or '—'}\n\n"
                "Достаточно ли материала скелета для полного урока, или "
                "нужен свежий поиск документации?"
            ),
        },
    ]


def build_teach_messages(
    skeleton: str,
    level: str,
    justification: str,
    search_results: list[dict],
) -> list[dict]:
    """Build the messages for unfolding the skeleton into a lesson (task 3.3).

    Pure function: the teacher prompt plus the skeleton, the per-level
    directive (distinct unfolding per level), the assessment justification
    (the gaps to close for ``partial``), and — when the docs decision asked
    for fresh material — the ``search_sdd_docs`` results block.
    """
    parts = [
        f"Скелет урока (ADR-009, секции фиксированы):\n\n{skeleton}",
        LEVEL_DIRECTIVES[level],
    ]
    if justification:
        parts.append(f"Пробелы ученика (из обоснования оценки): {justification}")
    if search_results:
        lines = "\n".join(
            f"- {result['title']} — {result['url']}\n  {result['content']}"
            for result in search_results
        )
        parts.append(f"Свежая документация (search_sdd_docs):\n{lines}")
    parts.append(
        "Разверни скелет в полный урок. Пиши по-русски, в markdown, "
        "сохрани секции скелета как структуру урока."
    )
    return [
        {"role": "system", "content": TEACH_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
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
