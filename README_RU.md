# SDD Trainer — ИИ-тренер по Spec-Driven Development

![Tests](https://github.com/Alex-Kul777/sdd-trainer/actions/workflows/tests.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Coverage](https://img.shields.io/badge/coverage-40%25%2B-yellowgreen)

## 📋 Описание

**SDD Trainer** — персональный ИИ-агент-тренер, который обучает методологии
**Spec-Driven Development (SDD)** и работе с **OpenSpec**: диалоговые уроки,
квизы с human-in-the-loop, сократические вопросы и память прогресса по доменам SDD
(сейчас — openspec-basics; роадмап остальных доменов —
[docs/roadmap.md](docs/roadmap.md)).

Тренер построен на **GigaChat** (OpenAI-совместимый API cloud.ru, ADR-005) и
**LangGraph**. Мета-идея проекта: он сам разрабатывается по OpenSpec — в
репозитории живёт `openspec/` со спеками и change-пропозалами. Тренер
преподаёт то, на чём построен сам.

## 🚀 Три фазы эволюции

| Фаза | Форма | Что умеет |
|------|-------|-----------|
| **1. Консоль** | Python CLI-агент | Диалоговое обучение: урок → квиз → сократический вопрос; память прогресса |
| **2. FastAPI** | REST-сервис | Тот же граф по HTTP: стриминг (ndjson), квизы через interrupt/HITL |
| **3. FastAPI + MCP** | Сервис + эндпоинт `/mcp` | Двунаправленная интеграция с OpenClaw: Telegram и дашборды — инфраструктура OpenClaw |

Принцип: один LangGraph-граф — нарастающий транспорт (консоль → HTTP → MCP).

## ✅ Критерии курса

| # | Критерий | Чем закрывается |
|---|----------|-----------------|
| 1 | GigaChat | OpenAI-совместимый API cloud.ru: `GigaChat/GigaChat-3-Pro` → fallback `GigaChat/GigaChat-3.5-Reasoning` (ADR-005) |
| 2 | LangGraph | Граф тренера: assess → route → teach/quiz/socratic |
| 3 | ≥2 tools внешних API | `search_sdd_docs` (Tavily), `read_openspec_examples` (GitHub API), `get_student_history` (OpenClaw) |
| 4 | Состояние/memory | SqliteSaver-чекпоинтер + `data/training-state.json` (ADR-008) |
| 5 | Роутинг ≥3 путей | routing node: knows_it / partial / new_topic (+ clarification) |
| 6 | FastAPI | REST + стриминг, фаза 2 (ADR-008) |

## 📁 Структура проекта

```
.
├── openspec/               # мета: сам проект по SDD (specs/ + changes/)
├── src/sdd_trainer/
│   ├── config.py           # GigaChatConfig: cloud.ru API (ADR-005)
│   ├── models.py           # Pydantic-схемы (AIA_02)
│   ├── core/               # llm_manager, graph, tools, memory
│   ├── lessons/            # домены с контентом (roadmap — в docs/roadmap.md)
│   ├── console/            # фаза 1: CLI
│   ├── api/                # фаза 2: FastAPI
│   └── mcp/                # фаза 3: MCP-эндпоинт
├── prompts/                # few-shot скелеты уроков
├── data/                   # training-state.json, чекпоинты
├── tests/                  # unit / integration / performance / fixtures
├── backlog/                # BKL-конвенция задач
├── docs/
├── .github/workflows/      # CI: tests.yml
├── app.py                  # точка входа CLI
└── Makefile, Dockerfile, docker-compose.yml, pytest.ini, setup.py, ...
```

## 🛠 Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env        # заполнить GIGACHAT_KEY (и TAVILY_API_KEY)
```

## ▶️ Запуск

```bash
python -m sdd_trainer                                # T1: живой диалог с GigaChat
python -m sdd_trainer --assess                       # T2: демо структурированной оценки уровня
python -m sdd_trainer --session [--student ИМЯ]      # T3: сеанс на графе — оценка → маршрут
                                                     # (knows_it/partial/new_topic/+clarification)
                                                     # → урок/квиз; память — чекпоинт SqliteSaver
                                                     # (thread_id student:<ИМЯ>, ADR-008)
```

Прерванный сеанс (`--session`, Ctrl-D/Ctrl-C) сохраняется в чекпоинт
`data/checkpoints.sqlite` и возобновляется с того же места при следующем
запуске с тем же `--student` (критерий курса 4).

## 🧪 Тесты

```bash
make test                   # все тесты
make test-unit              # только unit
pytest -v --cov             # с покрытием
```

CI (GitHub Actions) запускает тесты с покрытием на каждый push/PR в main.

## 📐 OpenSpec: разработка по методологии, которой обучает тренер

Каждая фаза — change proposal в `openspec/changes/` (ADR-003):

| Фаза | Change |
|------|--------|
| 0 | `add-project-skeleton` |
| 1 | `add-console-trainer` |
| 2 | `add-fastapi-service` |
| 3 | `add-mcp-integration` |

Цикл: propose → apply (коммиты со ссылками на tasks.md) → archive.

## 📚 Документация

- [GLOSSARY.md](GLOSSARY.md) — глоссарий домена
- [DECISIONS.md](DECISIONS.md) — архитектурные решения (ADR-001..008)
- [CHANGELOG.md](CHANGELOG.md) — история изменений
- [backlog/README.md](backlog/README.md) — конвенция задач BKL
- [README.md](README.md) — краткая версия на английском
