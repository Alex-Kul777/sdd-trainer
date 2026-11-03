"""Entry point for ``python -m sdd_trainer`` — console (T1 REPL + T2 demo + T3 session).

T1 (issue #2): thin end-to-end slice — console input → GigaChat via the
OpenAI-compatible cloud.ru API (ADR-005) → reply printed back.

T2 (issue #3): ``--assess`` — the trainer asks a calibration question, the
student's answer goes to GigaChat, and the structured ``Assessment`` (tools +
tool_choice, ADR-005) is printed.

T3 (issue #4): ``--session`` — a trainer session on the LangGraph graph:
assess → route (knows_it / partial / new_topic + clarification) → teach
(T4, issue #5: a real lesson unfolded from the ADR-009 skeleton under the
assessed level, with ``search_sdd_docs`` pulled on demand) → quiz (T5,
issue #6: questions from the authored JSON quiz, one interrupt per
question, deterministic token F1 against the reference answers, progress
recorded into training-state.json), with the selected route visible in
the session log and the state persisted by a SqliteSaver checkpointer
under the student thread id ``student:<name>`` (ADR-008, criterion 4).
The console is thin glue without business logic (design.md): it wires
the graph, drives the HITL loop (``interrupt`` → ``Command(resume=...)``),
prints the session log and a summary at exit; every decision lives in
the graph nodes.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Optional

from langgraph.types import Command
from openai import OpenAIError

from sdd_trainer.config import GigaChatConfig, trainer_config
from sdd_trainer.core.graph import build_graph
from sdd_trainer.core.llm_manager import LLMManager, StructuredOutputError
from sdd_trainer.core.memory import MemoryManager
from sdd_trainer.core.prompts import (
    ASSESSMENT_DOMAIN,
    ASSESSMENT_SYSTEM_PROMPT,
    CALIBRATION_QUESTION,
    build_assessment_messages,
)
from sdd_trainer.models import Assessment

# The prompt constants/builders above moved to ``core.prompts`` in T3; they
# are re-exported here so existing imports (tests, T2 demo) keep working.

EXIT_COMMANDS = {"q", "quit", "exit"}

SYSTEM_PROMPT = (
    "Ты — SDD Trainer, дружелюбный преподаватель Spec-Driven Development "
    "и OpenSpec. Отвечай кратко, по делу и на русском языке."
)

#: Default student name — the ADR-008 example thread id ``student:alex``.
DEFAULT_STUDENT = "alex"


def student_thread_id(name: str) -> str:
    """Build the LangGraph thread id from a student name (ADR-008).

    Convention: ``student:<name>``. The name is stripped and must be a
    single token (no whitespace) — it becomes part of the checkpoint key.
    """
    student = name.strip()
    if not student or any(char.isspace() for char in student):
        raise ValueError(f"недопустимое имя ученика: {name!r}")
    return f"student:{student}"


def find_pending_question(snapshot: Any) -> Optional[str]:
    """Extract the pending interrupt question from a graph state snapshot.

    Returns the payload of the first pending interrupt (the question the
    student was asked), or None when nothing is pending — used to resume an
    interrupted session from its checkpoint (criterion 4).
    """
    for task in snapshot.tasks:
        for pending in getattr(task, "interrupts", ()) or ():
            if pending.value is not None:
                return pending.value
    return None


def format_session_summary(state: dict, student: str, thread_id: str) -> list[str]:
    """Format the end-of-session summary lines (task 6.1).

    Pure function (unit-tested): renders whatever the final graph state
    holds — level, route, the unfolded lesson (T4), quiz stub (T5),
    clarification rounds — without touching the graph or the network.
    """
    lines = [
        "",
        "=== Итог сеанса ===",
        f"Ученик: {student} (thread_id: {thread_id})",
        f"Домен: {state.get('domain', '—')}",
    ]
    assessment = state.get("assessment")
    if assessment:
        lines.append(
            "Уровень: {} (уверенность {:.2f})".format(
                assessment["level"], assessment["confidence"]
            )
        )
        lines.append(f"Обоснование: {assessment['justification']}")
    route = state.get("route")
    if route:
        lines.append(f"Маршрут: {route['path']} — {route['reason']}")
    if state.get("teach_output"):
        lines.append(f"Урок: {state['teach_output']}")
    if state.get("quiz_output"):
        lines.append(f"Квиз: {state['quiz_output']}")
    rounds = state.get("clarification_rounds", 0)
    if rounds:
        lines.append(f"Уточняющих вопросов за сеанс: {rounds}")
    lines.append("Чекпоинт сохранён — сеанс можно продолжить с тем же --student.")
    return lines


def _ask(question: str) -> Optional[str]:
    """Print a graph question and read the student's answer (thin glue).

    Re-asks on empty input; returns None on EOF/Ctrl-C (the caller reports
    the saved checkpoint and exits).
    """
    print(f"\n[граф] {question}")
    while True:
        try:
            answer = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if answer:
            return answer
        print("Пустой ответ — попробуй ещё раз (Ctrl-D — выйти, сеанс сохранится).")


def _print_prior_log(values: dict) -> int:
    """Print log entries carried over from previous sessions (checkpoint).

    Returns the number of entries already shown, so the caller prints only
    the new ones as the session runs.
    """
    log = values.get("log") or []
    if log:
        print("\n[чекпоинт] История ученика (из чекпоинта):")
        for entry in log:
            print(f"  · {entry}")
    return len(log)


def _print_new_log(result: dict, printed: int) -> int:
    """Print log entries added since the last invoke; return the new count."""
    log = result.get("log") or []
    for entry in log[printed:]:
        print(f"\n[граф] {entry}")
    return len(log)


def _print_interrupted_exit(student: str, state: dict, thread_id: str) -> None:
    """Report an interrupted session: checkpoint saved, resume instructions."""
    print("\n[чекпоинт] Сеанс прерван — состояние сохранено в чекпоинте.")
    print(f"Перезапусти с тем же учеником (--student {student}), "
          "чтобы продолжить с того же места.")
    for line in format_session_summary(state, student, thread_id):
        print(line)


def run_session(config: GigaChatConfig, student: str) -> None:
    """T3 session (issue #4): drive the trainer graph in the console.

    Thin glue (task 6.1): wire ``MemoryManager`` (SqliteSaver, ADR-008) +
    ``LLMManager`` + ``build_graph``, then loop ``invoke`` → print new log
    entries → answer interrupts with ``Command(resume=...)`` until the graph
    reaches END. An interrupted session (Ctrl-D/Ctrl-C at a question) leaves
    a checkpoint; the next run with the same ``--student`` resumes it.
    """
    thread_id = student_thread_id(student)
    memory = MemoryManager(
        thread_id=thread_id, checkpoint_path=trainer_config.checkpoint_path
    )
    llm = LLMManager(config=config)
    graph = build_graph(llm, checkpointer=memory.get_checkpointer())
    thread_config = memory.thread_config()

    print("SDD Trainer — сеанс на графе (T3+T4+T5, issues #4/#5/#6)")
    print(f"Модель: {config.model} · endpoint: {config.base_url} (ADR-005)")
    print(f"Ученик: {student} · thread_id: {thread_id} (ADR-008)")
    print(f"Чекпоинтер: {trainer_config.checkpoint_path} (SqliteSaver)")
    print("Выход в любой момент: Ctrl-D — сеанс сохранится и возобновится.")

    try:
        snapshot = graph.get_state(thread_config)
        printed = _print_prior_log(snapshot.values)

        if snapshot.next:
            print("\n[чекпоинт] Найден незавершённый сеанс — "
                  "возобновляю с чекпоинта (критерий 4).")
            question = find_pending_question(snapshot)
            if question is not None:
                answer = _ask(question)
                if answer is None:
                    _print_interrupted_exit(
                        student, snapshot.values, thread_id
                    )
                    return
                result = graph.invoke(Command(resume=answer), thread_config)
            else:
                # Pending work without a stored question (e.g. a crashed
                # step): let the graph continue by itself; if it interrupts
                # again, the loop below re-asks the question.
                result = graph.invoke(None, thread_config)
        else:
            result = graph.invoke({"domain": ASSESSMENT_DOMAIN}, thread_config)

        while True:
            printed = _print_new_log(result, printed)
            interrupts = result.get("__interrupt__")
            if not interrupts:
                break
            answer = _ask(interrupts[0].value)
            if answer is None:
                _print_interrupted_exit(
                    student, graph.get_state(thread_config).values, thread_id
                )
                return
            result = graph.invoke(Command(resume=answer), thread_config)

        final_state = graph.get_state(thread_config).values
        for line in format_session_summary(final_state, student, thread_id):
            print(line)
    except OpenAIError as exc:
        print(f"\n[GigaChat недоступен: {exc}]")
        print("Чекпоинт хранит последний завершённый шаг — "
              "перезапусти сеанс с тем же --student.")
        sys.exit(1)
    except StructuredOutputError as exc:
        print(f"\n[Модель не вернула валидную структуру: {exc}]")
        print("Чекпоинт хранит последний завершённый шаг — "
              "перезапусти сеанс с тем же --student.")
        sys.exit(1)
    finally:
        memory.close()


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
    """Dispatch console modes: ``--session`` (T3), ``--assess`` (T2), T1 REPL."""
    parser = argparse.ArgumentParser(
        prog="sdd_trainer",
        description="SDD Trainer — консольный тренер SDD/OpenSpec",
    )
    parser.add_argument(
        "--assess",
        action="store_true",
        help="демо T2: калибровочный вопрос → структурированная оценка уровня (Assessment)",
    )
    parser.add_argument(
        "--session",
        action="store_true",
        help="сеанс T3 на графе: оценка → маршрут (knows_it/partial/new_topic/"
        "+clarification) → урок → квиз с F1-оценкой, память через чекпоинт "
        "и training-state (issues #4/#5/#6)",
    )
    parser.add_argument(
        "--student",
        default=DEFAULT_STUDENT,
        help="имя ученика для --session: thread_id student:<name> и чекпоинт "
        "(ADR-008; по умолчанию alex)",
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

    if args.session:
        run_session(config, args.student)
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
