"""Entry point for ``python -m sdd_trainer`` — console REPL (T1 прокол).

T1 scope (issue #2): the thinnest end-to-end slice — console input →
GigaChat via the OpenAI-compatible cloud.ru API (ADR-005) → reply printed
back. The LangGraph-based trainer REPL (add-console-trainer task 6.1)
replaces this thin glue later in phase 1.
"""
from __future__ import annotations

import sys

from openai import OpenAIError

from sdd_trainer.config import GigaChatConfig
from sdd_trainer.core.llm_manager import LLMManager

EXIT_COMMANDS = {"q", "quit", "exit"}

SYSTEM_PROMPT = (
    "Ты — SDD Trainer, дружелюбный преподаватель Spec-Driven Development "
    "и OpenSpec. Отвечай кратко, по делу и на русском языке."
)


def main() -> None:
    """Run the console REPL: input -> GigaChat -> print (T1)."""
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
