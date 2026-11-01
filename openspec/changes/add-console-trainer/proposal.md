# Proposal: Add Console Trainer (Phase 1)

**Phase:** 1 — консольный агент
**Effort:** 2 дня (2–3 ноября)
**Источники:** GitHub Issue #1 (спека фичи); PLAN-FINAL-PROJECT.md разделы 4–6; ADR-005, ADR-006, ADR-008, ADR-009; мини-раунды 3–4 grilling-протокола

## Problem

Ученику курса не хватает практики и обратной связи по SDD/OpenSpec: после
уроков неизвестно, что усвоено. Скелет репозитория (фаза 0) поведения не
содержит: граф, клиент GigaChat, tools и персистентность — заглушки.
Консультация 3 ноября требует показать работающий граф с роутингом.

## Solution

Первый вертикальный срез тренера — домен «OpenSpec-основы» end-to-end:

- LangGraph-граф assess → route → teach → quiz (без interrupt): пассивная
  оценка уровня, роутинг knows_it / partial / new_topic (+ clarification),
  урок из скелета, квиз с F1-оценкой против эталонов;
- llm_manager: GigaChat через OpenAI-совместимый API cloud.ru (ADR-005),
  structured output через tools + tool_choice, fallback-модель;
- tools: analyze_student_repo (репозиторий ученика) + search_sdd_docs
  (Tavily, ADR-006) — критерий 3;
- персистентность: SqliteSaver + thread_id ученика, training-state.json
  (ADR-008) — критерий 4;
- контент домена openspec-basics: markdown-скелет + JSON-квиз (ADR-009);
- консольный REPL поверх графа.

## Scope

**Внутри:** граф, клиент, 2 tools, чекпоинтер, training-state, контент
openspec-basics, консоль, unit-тесты (FakeLLM), integration-тесты (skip без
ключа), ручной смоук-чеклист.

**Вне scope:** HITL-квизы через interrupt и сократический узел (фаза 1.5),
get_student_history (фаза 3), FastAPI (фаза 2, `add-fastapi-service`), MCP
(фаза 3, `add-mcp-integration`), остальные 5 доменов, spaced repetition.
