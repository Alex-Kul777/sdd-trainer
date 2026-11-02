"""Entry point for ``python -m sdd_trainer`` — console (T1 REPL + T2 demo).

T1 (issue #2): thin end-to-end slice — console input → GigaChat via the
OpenAI-compatible cloud.ru API (ADR-005) → reply printed back.

T2 (issue #3): ``--assess`` — the trainer asks a calibration question, the
student's answer goes to GigaChat, and the structured ``Assessment`` (tools +
tool_choice, ADR-005) is printed. No graph yet — the LangGraph-based trainer
REPL (add-console-trainer task 6.1) replaces the thin glue later in phase 1.
"""
from __future__ import annotations

import argparse
import sys

from openai import OpenAIError

from sdd_trainer.config import GigaChatConfig
from sdd_trainer.core.llm_manager import LLMManager, StructuredOutputError
from sdd_trainer.models import Assessment

EXIT_COMMANDS = {"q", "quit", "exit"}

SYSTEM_PROMPT = (
    "Ты — SDD Trainer, дружелюбный преподаватель Spec-Driven Development "
    "и OpenSpec. Отвечай кратко, по делу и на русском языке."
)

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


def build_assessment_messages(student_answer: str) -> list[dict]:
    """Build the chat messages for the structured assessment call (T2).

    Pure function (unit-tested): the assessment system prompt plus one user
    message carrying the calibration question and the student's answer.
    Shared by the ``--assess`` demo and the live integration tests.
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


def run_assessment(config: GigaChatConfig) -> None:
    """T2 demo (issue #3): calibration question → GigaChat → printed Assessment."""
    print("SDD Trainer — демо структурированной оценки уровня (T2, issue #3)")
    print(f"Модель: {config.model} · fallback: {config.fallback_model}")
    print(f"Домен: {ASSESSMENT_DOMAIN} · endpoint: {config.base_url} (ADR-005)")
    print()
    print("Калибровочный вопрос:")
    print(f"  {CALIBRATION_QUESTION}")
    print()
    try:
        student_answer = input("Ваш ответ: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nДо встречи!")
        return
    if not student_answer:
        print("Пустой ответ — оценку не запускаю. До встречи!")
        return

    print("\nОцениваю ответ через GigaChat (structured output: tools + tool_choice)…")
    manager = LLMManager(config=config)
    try:
        assessment = manager.llm_call(
            build_assessment_messages(student_answer), Assessment
        )
    except StructuredOutputError as exc:
        print(f"\n[Модель не вернула валидную структуру Assessment: {exc}]")
        sys.exit(1)
    except OpenAIError as exc:
        print(f"\n[GigaChat недоступен: {exc}]")
        print("Проверьте ключ в .env и попробуйте ещё раз.")
        sys.exit(1)

    print("\nОценка уровня ученика (Assessment):")
    print(f"  level:       {assessment.level}")
    print(f"  обоснование: {assessment.justification}")
    print(f"  confidence:  {assessment.confidence}")
    print(f"  домен:       {assessment.domain}")
    print()
    print("Структурированный результат (JSON):")
    print(assessment.model_dump_json(indent=2, ensure_ascii=False))


def main() -> None:
    """Dispatch console modes: ``--assess`` (T2 demo) or the T1 dialogue REPL."""
    parser = argparse.ArgumentParser(
        prog="sdd_trainer",
        description="SDD Trainer — консольный тренер SDD/OpenSpec",
    )
    parser.add_argument(
        "--assess",
        action="store_true",
        help="демо T2: калибровочный вопрос → структурированная оценка уровня (Assessment)",
    )
    args = parser.parse_args()

    config = GigaChatConfig()
    if not config.is_configured():
        print("SDD Trainer: не найден ключ GIGACHAT_KEY.")
        print("Скопируйте .env.example в .env и заполните GIGACHAT_KEY")
        print("(ключ cloud.ru, ADR-005):")
        print()
        print("    cp .env.example .env")
        print()
        print(".env уже в .gitignore — ключ никогда не попадёт в git.")
        sys.exit(1)

    if args.assess:
        run_assessment(config)
        return

    manager = LLMManager(config=config, system_prompt=SYSTEM_PROMPT)
    print("SDD Trainer — консольный тренер SDD/OpenSpec (T1: живой диалог)")
    print(f"Модель: {config.model} · endpoint: {config.base_url} (ADR-005)")
    print("Выход: q / quit / exit или Ctrl-D")
    print()

    while True:
        try:
            user_input = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nДо встречи!")
            break

        if not user_input:
            continue
        if user_input.lower() in EXIT_COMMANDS:
            print("До встречи!")
            break

        try:
            reply = manager.chat(user_input)
        except OpenAIError as exc:
            print(f"\n[GigaChat недоступен: {exc}]")
            print("Проверьте ключ в .env и попробуйте ещё раз.\n")
            continue

        print(f"\nGigaChat: {reply}\n")


if __name__ == "__main__":
    main()
