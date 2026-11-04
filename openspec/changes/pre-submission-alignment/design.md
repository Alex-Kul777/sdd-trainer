# Design: Pre-Submission Alignment

## Решения владельца (2026-11-04, после ревью)

| # | Отклонение | Варианты | Решение |
|---|---|---|---|
| 1 | ADR-010 нет в DECISIONS.md | (a) добавить / (b) оставить в архиве | **1a** |
| 2 | ADR-001: FastAPI vs stdio-only | (a) superseded / (b) реализовать / (c) спросить курс | **2b** |
| 3 | ADR-007: pass-заглушка | (a) deferred / (b) реализовать / (c) удалить | **3b** |
| 4 | LESSON_DOMAINS без рабочего домена | (a) добавить 7-й / (b) сузить до реальности | **4b** |

Ключевое следствие выбора 2b/3b: **код подтягивается к ADR** — ADR-001 и
ADR-007 остаются accepted и наконец соблюдены; статусы менять не нужно.
Единственное изменение — появление ADR-010 в DECISIONS.md.

## D1: ADR-010 → DECISIONS.md (T1)

Формат — как у существующих записей (### / Date / Status / Context /
Decision / Consequences). Источник — архивированный design.md
(`archive/2026-11-03-add-mcp-integration/design.md`). Пометка о запоздалом
переносе — честная запись находки ревью.

## D2: FastAPI HTTP-интерфейс (T2)

- Один процесс: FastAPI-приложение — хребет; MCP Streamable HTTP
  монтируется в него (`FastMCP.streamable_http_app()` → `app.mount("/mcp")`)
  — буквально ADR-001. stdio-сервер (ADR-010) остаётся fallback.
- REST повторяет семантику MCP-инструментов (ADR-010: пошаговое
  возобновление графа): `POST /sessions/{student}/start`,
  `POST /sessions/{student}/answer` — sync; `GET /sessions/{student}/stream`
  — SSE-стриминг; `GET /health`.
- Ядро не переписывается: тот же граф, SqliteSaver, thread_id (ADR-008),
  `Command(resume=answer)` — как в `mcp/server.py`.
- Режимы по AIA_07: синхронный запуск графа + стриминговый + HITL через
  interrupt/Command.
- Зависимости: fastapi, uvicorn добавляются в requirements.txt
  (существующие пины не трогать).

## D3: get_student_history (T3)

- ADR-007: тренер сам тянет данные — `openclaw sessions` subprocess.
- CLI: `openclaw sessions --json` (флаг существует, проверено 04.11);
  точную команду и формат выбирает реализация по `--help`
  (пиновать формат, парсить аккуратно — ADR-007).
- Graceful degradation: CLI отсутствует/ошибка → пустой результат
  с пояснением, не исключение (тренер не должен падать из-за среды).
- Тесты: mock subprocess, без сети, без реальных вызовов CLI.

## D4: LESSON_DOMAINS → реальность (T4)

- `LESSON_DOMAINS = ["openspec-basics"]` — единственный домен с контентом
  (скелет `prompts/lessons/openspec-basics.md`, квиз
  `data/quizzes/openspec-basics.json`).
- Шесть доменов-роадмапа → `docs/roadmap.md` (Phase 3 curriculum).
- Тест `test_skeleton.py` обновляется: `len == 1`, openspec-basics в списке.
- Греп остальных упоминаний шести доменов — поправить/перенести
  (`openspec/changes/*` — историческая запись, не трогать).

## Риски

- T2 — самый большой кусок (новый модуль + тесты): запускается с
  максимальным запасом времени; стриминг — по образцу AIA_07.
- Параллельная работа трёх субагентов в одном дереве: непересекающиеся
  скоупы файлов; каждый гоняет только свои тесты
  (`COVERAGE_FILE=/tmp/cov-tN/.coverage`); полный гейт — родитель
  после всех.
