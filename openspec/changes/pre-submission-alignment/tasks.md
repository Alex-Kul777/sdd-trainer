# Tasks: Pre-Submission Alignment

## T1: ADR-010 → DECISIONS.md (docs)

- [x] 1.1 Добавить ADR-010 в DECISIONS.md в формате существующих записей;
      источник — `archive/2026-11-03-add-mcp-integration/design.md`;
      пометка о запоздалом переносе (находка ревью 04.11). Выполнено
      родителем до старта субагентов.

## T2: FastAPI HTTP-интерфейс (ADR-001)

- [x] 2.1 Проверить метод streamable-http у FastMCP в mcp==1.27.1 (импорт)
- [x] 2.2 Тесты (сначала): TestClient + FakeOpenAI — /health, start, answer
- [x] 2.3 Модуль `src/sdd_trainer/app.py`: FastAPI, /health, sync-эндпоинты
- [x] 2.4 SSE-стриминг `GET /sessions/{student}/stream` (паттерн AIA_07)
- [x] 2.5 Монтирование MCP: `streamable_http_app()` → `app.mount("/mcp")`
- [x] 2.6 requirements.txt: + fastapi, uvicorn (существующие пины не трогать)

## T3: get_student_history (ADR-007)

- [x] 3.1 Изучить `openclaw sessions --help` / `--json` (read-only)
- [x] 3.2 Тесты (сначала): mock subprocess — parse, empty, CLI отсутствует
- [x] 3.3 Реализация в `core/tools.py`: subprocess + defensive парсинг +
      graceful degradation; docstring больше не «phase 3»

## T4: LESSON_DOMAINS → реальность

- [x] 4.1 Тесты (сначала): `len == 1`, openspec-basics в списке
- [x] 4.2 `lessons/__init__.py`: `LESSON_DOMAINS = ["openspec-basics"]`
- [x] 4.3 `docs/roadmap.md`: шесть доменов как Phase 3 curriculum
- [x] 4.4 Греп упоминаний шести доменов по репо — поправить/перенести
      (`openspec/changes/*` не трогать)
