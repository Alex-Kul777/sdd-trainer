# Proposal: Pre-Submission Alignment

## Why

Ревью перед сдачей (2026-11-04, навык code-review-two-axis, отчёт:
`notes/review-pre-submission.md` в workspace агента) выявило четыре
отклонения кода и документации от собственных архитектурных решений
(ADR-001, ADR-007, ADR-010, curriculum). Дедлайн сдачи — 2026-11-13.
Владелец выбрал разрешения 2026-11-04: **1a, 2b, 3b, 4b** — код
подтягивается к ADR, а не наоборот.

## What Changes

1. **ADR-010 → DECISIONS.md** (T1). Архивация `add-mcp-integration`
   прошла 2026-11-03 (48e7ee5), но шаг переноса ADR-010 в single-file
   ADR-дом был пропущен: код ссылается на ADR-010 ~27 раз, в DECISIONS.md
   его нет.
2. **FastAPI HTTP-интерфейс** (T2). ADR-001 (accepted) требует один
   FastAPI-процесс: REST + MCP-эндпоинт `/mcp` (Streamable HTTP,
   `FastMCP.streamable_http_app()` → `app.mount`). Реализован только
   stdio (ADR-010). T2 закрывает ADR-001 буквально и критерий 6 курса
   в исходной формулировке (синхронный + стриминговый режимы).
3. **get_student_history** (T3). ADR-007 (accepted) описывает pull
   истории ученика через `openclaw sessions` subprocess; в коде —
   pass-заглушка «phase 3» (`core/tools.py:100`).
4. **LESSON_DOMAINS → реальность** (T4). Рабочий домен `openspec-basics`
   отсутствует в `LESSON_DOMAINS` (шесть доменов-роадмапа без контента);
   тест запинил `len == 6`. T4 синхронизирует список с реальностью
   и выносит роадмап в `docs/roadmap.md`.

## Capabilities

### ADDED
- `http-trainer` — REST + MCP Streamable HTTP в одном FastAPI-процессе
- `student-history` — pull истории ученика через openclaw CLI
- `curriculum` — единственный домен с контентом; роадмап отделён

## Impact

- Код: новый FastAPI-модуль, реализация одного tool, правка списка доменов
- Зависимости: + fastapi, uvicorn (новые пины; существующие не трогаем)
- Документация: DECISIONS.md (+ADR-010), docs/roadmap.md (новый)
- ADR-001 и ADR-007 остаются accepted — после T2/T3 они соблюдены буквально
