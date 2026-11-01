# Proposal: Add Project Skeleton (Phase 0)

**Phase:** 0 — каркас репозитория
**Effort:** 1 день (2 ноября)
**Источники:** PLAN-FINAL-PROJECT.md, разделы 7 и 9; ADR-002, ADR-003, ADR-005, ADR-008

## Problem

Курсовой проект «SDD Trainer» (ИИ-тренер по Spec-Driven Development) начинается
с пустого места. Курс требует GigaChat, LangGraph, tools, память, роутинг и
FastAPI; сдача — 13 ноября 2026. Нужен воспроизводимый каркас репозитория с
проверенными конвенциями, чтобы фазы 1–3 добавляли поведение, а не
инфраструктуру. Образец конвенций — собственный репозиторий rag_GigaChat
(ADR-002): src-лейаут, GigaChatConfig-паттерн, лейаут тестов, CI, backlog BKL.

## Solution

Создать скелет строго по разделу 7.2 плана:

- src-лейаут `src/sdd_trainer/`: модули-заглушки с docstrings (core/, lessons/,
  console/, api/, mcp/) — без вызовов API;
- `config.py`: `GigaChatConfig` — GigaChat через OpenAI-совместимый API cloud.ru
  (ADR-005), модели `GigaChat/GigaChat-3-Pro` → fallback
  `GigaChat/GigaChat-3.5-Reasoning`; `TrainerConfig` — пути персистентности
  (ADR-008);
- инфраструктура: requirements.txt, setup.py, pytest.ini, .coveragerc, Makefile,
  Dockerfile, docker-compose.yml, CI `tests.yml` (адаптация под src-лейаут);
- тесты: conftest.py + unit-тесты конфигурации + import-smoke тест;
- документация: README.md (EN), README_RU.md (основной), CHANGELOG.md,
  CONTEXT.md, DECISIONS.md в корне репо;
- мета: `openspec init` + данный change proposal (ADR-003: change-per-phase).

## Scope

**Внутри:** структура раздела 7.2, конфигурация, заглушки модулей, CI, openspec
init, приватный GitHub-репозиторий Alex-Kul777/sdd-trainer.

**Вне scope:** реализация графа и вызовы GigaChat (фаза 1,
`add-console-trainer`), FastAPI-эндпоинты (фаза 2, `add-fastapi-service`),
MCP-интеграция (фаза 3, `add-mcp-integration`), смоук-тесты с реальным API.
