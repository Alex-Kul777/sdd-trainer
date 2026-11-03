"""Живое демо MCP-тренера: SDK-клиент прогоняет полный сеанс (M2, issue #10).

Запуск::

    .venv/bin/python scripts/mcp_demo.py [--student ИМЯ] [--answer ОТВЕТ]

Клиент поднимает реальный сервер (``python -m sdd_trainer.mcp``) как
subprocess по stdio — как это сделала бы любая MCP-хост-программа (Claude
Desktop, Cline, OpenClaw) — и проходит полный сеанс: калибровочный вопрос →
вердикт оценки + маршрут (+ уточняющие вопросы при низкой уверенности) →
урок → квиз по одному вопросу за вызов → F1-вердикт (порог 0.60) →
записанный прогресс. Транскрипт печатается на консоль клиента; stdout
сервера принадлежит MCP-протоколу и остаётся чистым. Это автодемо для
скринкаста (M3, issue #11).

Демо-ученик отвечает на квиз эталонными ответами из авторского квиза
(детерминированный зачёт — воспроизводимый скринкаст); чистый прогон с
нуля — свежее значение --student: перезапуск с тем же именем продолжит
сеанс с чекпоинта (ADR-008).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DEFAULT_STUDENT = "demo"

DEFAULT_ANSWER = (
    "OpenSpec — инструмент spec-driven development. В specs/ лежат стабильные "
    "спецификации требований (source of truth), в changes/ — change proposals: "
    "предложения изменений с proposal.md, design.md, tasks.md и дельтой спеки. "
    "Proposal проходит review, применяется и архивируется, а спецификация "
    "остаётся источником истины."
)

CLARIFICATION_ANSWER = (
    "Знаком со структурой specs/ и changes/, писал tasks.md для proposal, "
    "но с дельтами спецификаций почти не работал."
)


def _quiz_answers(domain: str = "openspec-basics") -> list[str]:
    """Эталонные ответы квиза — детерминированный зачёт для скринкаста.

    Демо-ученик отвечает референсами из data/quizzes/<domain>.json: F1 по
    ним равен 1.0, вердикт воспроизводим от прогона к прогону (ADR-009).
    Реальный ученик отвечал бы своими словами — серверу всё равно, он
    принимает любой текст ответа.
    """
    from sdd_trainer.lessons import load_quiz

    return [q.reference_answer for q in load_quiz(domain).questions]


def _server_params() -> StdioServerParameters:
    """Параметры subprocess: тот же интерпретатор, пакетная точка входа.

    В дочерний процесс уходят только переменные окружения тренера
    (сервер дополнительно читает .env сам); значения ключей не печатаются.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key.startswith(("GIGACHAT_", "TAVILY_", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"))
    }
    return StdioServerParameters(
        command=sys.executable, args=["-m", "sdd_trainer.mcp"], env=env
    )


def _payload(result) -> dict:
    """Разобрать результат вызова инструмента в dict (ошибки — громко)."""
    if result.isError:
        raise RuntimeError(f"Инструмент вернул ошибку: {result.content}")
    return json.loads(result.content[0].text)


def _print_question(payload: dict) -> None:
    """Напечатать вопрос графа в транскрипт демо."""
    print(f"\n[тренер] ({payload['question_kind']}-вопрос)")
    print(f"{payload['question']}")


def _print_verdict(payload: dict) -> None:
    """Напечатать вердикт оценки, маршрут и развёрнутый урок."""
    assessment = payload.get("assessment") or {}
    route = payload.get("route") or {}
    print("\n=== Вердикт оценки ===")
    print(f"Уровень:      {assessment.get('level', '—')}")
    print(f"Уверенность:  {assessment.get('confidence', '—')}")
    print(f"Обоснование:  {assessment.get('justification', '—')}")
    print(f"Маршрут:      {route.get('path', '—')} — {route.get('reason', '')}")
    if payload.get("lesson"):
        print("\n=== Урок ===")
        print(payload["lesson"])


def _print_quiz_verdict(payload: dict) -> None:
    """Напечатать F1-вердикт квиза и журнал сеанса (итог)."""
    quiz = payload.get("quiz") or {}
    print("\n=== Вердикт квиза (F1, ADR-009) ===")
    print(f"Домен:          {quiz.get('domain', '—')}")
    print(f"Счёт:           {quiz.get('score', 0.0):.2f} (порог 0.60)")
    print(f"Итог:           {'зачтён' if quiz.get('passed') else 'не зачтён'}")
    print(f"Обратная связь: {quiz.get('feedback', '—')}")
    if payload.get("log"):
        print("\n[журнал сеанса]")
        for entry in payload["log"]:
            print(f"  · {entry}")


def _print_progress(payload: dict) -> None:
    """Напечатать записанный прогресс ученика (training-state, ADR-008)."""
    print("\n=== Прогресс (training-state) ===")
    domains = payload.get("domains") or {}
    if not domains:
        print("  Доменов пока нет — квизов ещё не было.")
        return
    for domain, entry in sorted(domains.items()):
        print(
            "  · {}: счёт {:.2f}, серия {}, уроков завершено {}".format(
                domain,
                entry.get("score", 0.0),
                entry.get("streak", 0),
                entry.get("completed_lessons", 0),
            )
        )


async def _run_demo(student: str, answer: str) -> None:
    """Прогнать полный сеанс через реальный MCP-сервер по stdio."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("SDD Trainer — живое демо MCP (issue #10, M2)")
            print(f"Сервер: python -m sdd_trainer.mcp (stdio, ADR-010)")
            print(
                "Инструменты: "
                + ", ".join(sorted(tool.name for tool in tools.tools))
            )
            print(f"Ученик: {student} (thread_id student:{student}, ADR-008)")

            start = _payload(
                await session.call_tool("start_session", {"student": student})
            )
            if start["type"] == "error":
                raise RuntimeError(start["message"])
            if start["resumed"]:
                print("\n[чекпоинт] Незавершённый сеанс возобновлён (ADR-008).")
            _print_question(start)

            print("\n[ученик] " + answer)
            payload = _payload(
                await session.call_tool(
                    "answer_calibration", {"student": student, "answer": answer}
                )
            )
            for _ in range(3):  # граф ограничивает уточнения двумя раундами
                if payload["type"] == "error":
                    raise RuntimeError(payload["message"])
                if payload.get("question_kind") != "clarification":
                    break
                _print_question(payload)
                print("\n[ученик] " + CLARIFICATION_ANSWER)
                payload = _payload(
                    await session.call_tool(
                        "answer_clarification",
                        {"student": student, "answer": CLARIFICATION_ANSWER},
                    )
                )

            if payload["type"] == "error":
                raise RuntimeError(payload["message"])
            _print_verdict(payload)

            if payload.get("question_kind") != "quiz":
                print("\n[демо] Сеанс не дошёл до квиза — продолжи с тем же --student.")
                return
            _print_question(payload)  # первый вопрос квиза уже в payload
            for quiz_answer in _quiz_answers():
                print("\n[ученик] " + quiz_answer)
                payload = _payload(
                    await session.call_tool(
                        "answer_quiz_question",
                        {"student": student, "answer": quiz_answer},
                    )
                )
                if payload["type"] == "error":
                    raise RuntimeError(payload["message"])
                if payload["type"] == "question":
                    _print_question(payload)

            _print_quiz_verdict(payload)
            progress = _payload(
                await session.call_tool("get_progress", {"student": student})
            )
            if progress["type"] == "error":
                raise RuntimeError(progress["message"])
            _print_progress(progress)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp_demo",
        description="Живое демо: MCP-клиент прогоняет полный сеанс тренера "
        "(калибровка → оценка → урок → квиз → F1-вердикт → прогресс)",
    )
    parser.add_argument(
        "--student", default=DEFAULT_STUDENT,
        help="имя ученика (thread_id student:<name>, по умолчанию demo)",
    )
    parser.add_argument(
        "--answer", default=DEFAULT_ANSWER,
        help="ответ на калибровочный вопрос (по умолчанию — знающий ответ)",
    )
    args = parser.parse_args()

    try:
        anyio.run(_run_demo, args.student, args.answer)
    except RuntimeError as exc:
        print(f"\n[демо прервано: {exc}]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
