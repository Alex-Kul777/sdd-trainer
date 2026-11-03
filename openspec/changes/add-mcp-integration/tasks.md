# Tasks: Add MCP Integration (Phase 2)

## 1. MCP tracer bullet: сервер + assess-сессия end-to-end (M1, issue #9)

- [x] 1.1 FastMCP-сервер (stdio): точка входа `python -m sdd_trainer.mcp`, минимальный каркас
- [x] 1.2 Инструменты start_session + answer_calibration (+ clarification): калибровочный вопрос → вердикт + маршрут, пошаговое возобновление с чекпоинта (ADR-008/ADR-010)
- [x] 1.3 Живое демо: SDK MCP-клиент прогоняет assess-сессию end-to-end (unit — FakeLLM; integration — GigaChat, skip без ключа)

## 2. Полный набор инструментов (M2, issue #10)

- [ ] 2.1 Урок и квиз пошагово через MCP: ответ → следующий вопрос или F1-вердикт (порог 0.60)
- [ ] 2.2 Прямые tools: analyze_repo, search_docs
- [ ] 2.3 get_progress: training-state (domain, score, streak, completed lessons)

## 3. Смоук и скринкаст прототипа (M3, issue #11)

- [ ] 3.1 Смоук-чеклист MCP: полный сеанс тренера через MCP-клиент, критерии видны
- [ ] 3.2 Скринкаст-сценарий MCP-прототипа для сдачи (по образцу docs/smoke-checklist.md)
- [ ] 3.3 Suite зелёный, coverage-гейт 40%, tasks.md честный
