"""Живое демо MCP-тренера: SDK-клиент прогоняет assess-сессию end-to-end (task 1.3).

Запуск::

    .venv/bin/python scripts/mcp_demo.py [--student ИМЯ] [--answer ОТВЕТ]

Клиент поднимает реальный сервер (``python -m sdd_trainer.mcp``) как
subprocess по stdio — как это сделала бы любая MCP-хост-программа (Claude
Desktop, Cline, OpenClaw) — и проходит сеанс оценки: калибровочный вопрос →
ответ ученика → вердикт оценки + маршрут (+ уточняющие вопросы при низкой
уверенности модели). Транскрипт печатается на консоль клиента; stdout
сервера принадлежит MCP-протоколу и остаётся чистым. Это автодемо для
скринкаста (M3, issue #11); квиз-шаги — M2 (issue #10).
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


def _server_params() -> StdioServerParameters:
    """Параметры subprocess: тот же интерпретатор, пакетная точка входа.

    В дочерний процесс уходят только переменные окружения тренера
    (сервер дополнительно читает .env сам); значения ключей не печатаются.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key.startswith(("GIGACHAT_", "TAVILY_"))
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
    """Напечатать вердикт оценки и маршрут (итог assess-сессии)."""
    assessment = payload.get("assessment") or {}
    route = payload.get("route") or {}
    print("\n=== Вердикт оценки ===")
    print(f"Уровень:      {assessment.get('level', '—')}")
    print(f"Уверенность:  {assessment.get('confidence', '—')}")
    print(f"Обоснование:  {assessment.get('justification', '—')}")
    print(f"Маршрут:      {route.get('path', '—')} — {route.get('reason', '')}")
    if payload.get("log"):
        print("\n[журнал сеанса]")
        for entry in payload["log"]:
            print(f"  · {entry}")
    if payload.get("question_kind") == "quiz":
        print(
            "\n[демо M1] Оценка завершена: следующий шаг — вопрос квиза "
            "(инструменты квиза — M2, issue #10). Сеанс сохранён в чекпоинте: "
            "перезапуск с тем же --student продолжит с того же места."
        )


async def _run_demo(student: str, answer: str) -> None:
    """Прогнать assess-сессию через реальный MCP-сервер по stdio."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("SDD Trainer — живое демо MCP (issue #9, task 1.3)")
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


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp_demo",
        description="Живое демо: MCP-клиент прогоняет assess-сессию тренера",
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
