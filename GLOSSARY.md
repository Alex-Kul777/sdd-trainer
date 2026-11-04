# SDD Trainer — Domain Model (GLOSSARY.md)

Глоссарий домена проекта «SDD Trainer». Обновляется в ходе grilling-сессий.
Конвенция mattpocock/skills: GLOSSARY.md (глоссарий) + DECISIONS.md (ADRs) в корне репо. Переименован из CONTEXT.md 2026-11-01 (setup-matt-pocock-skills).

## SDD (Spec-Driven Development)
Методология: спецификация — источник истины, план до кода. Fluid/итеративный, built for brownfield. Тренер обучает ей.

## OpenSpec
Инструмент SDD: структура `openspec/` в репо (specs/ + changes/) + CLI (установлен локально, v1.14.0). Workflow: explore → propose → apply → archive.

## Spec (спецификация)
`openspec/specs/<capability>/spec.md` — стабильные требования. Формат: `## Purpose` + `### Requirement:` с **SHALL** + `#### Scenario:` **WHEN/THEN**.

## Change proposal
`openspec/changes/<kebab-case>/` — proposal.md (зачем) + design.md (как) + tasks.md (чек-лист) + specs/ (дельта ADDED/MODIFIED). Единица работы мета-процесса: 1 фаза = 1 change (ADR-003).

## Домен (lesson domain)
Учебная тема тренера. Готовый домен — openspec-basics (скелет + квиз, ADR-009); ещё 6 доменов — роадмап Phase 3 ([docs/roadmap.md](docs/roadmap.md)). Прогресс — в training-state.json.

## Lesson skeleton (скелет урока)
Заготовка урока домена с фиксированными секциями (Goal / Key concepts / Socratic questions / Examples / Quiz ref). GigaChat разворачивает скелет в полный урок под уровень ученика. Формат и расположение файлов — ADR-009.

## Quiz reference answers (эталоны)
Эталонные ответы квиза домена: база воспроизводимого F1-скоринга и structured output при проверке ответа ученика. Формат и расположение — ADR-009.

## Training-state
`data/training-state.json` — прогресс ученика: domain, score, streak (паттерн openclaw-tutor).

## Пассивная оценка (passive assessment)
Определение уровня ученика до вопросов: анализ репозитория (`analyze_student_repo`), истории сессий (`get_student_history`), собственного репо тренера (рекурсия). Паттерн openclaw-tutor.

## Граф тренера
LangGraph-граф: assess → route → teach/quiz/socratic. Шаблон — роутинг-агент AIA_06 (7 узлов). Роутинг ≥3 путей — критерий №5.

## Routing node
Узел выбора пути: knows_it / partial / new_topic (+ clarification). Критерий №5.

## HITL / interrupt
Human-in-the-loop: квизы через `interrupt` + `Command` (AIA_03/07). В консоли — input(), в FastAPI — приостановка графа с возобновлением ответом.

## Чекпоинтер (checkpointer)
LangGraph-персистентность состояния графа (SqliteSaver) — критерий №4.

## GigaChat
LLM курса. Модели: **GigaChat/GigaChat-3-Pro** (приоритет) → **ai-sage/GigaChat3.5-432B-A28B-Reasoning** (fallback; точные ID подтверждены живым models.list 02.11.2026, add-console-trainer 1.1) — подтверждено PDF + ноутбуком курса. Интеграция: **OpenAI-совместимый API** `https://foundation-models.api.cloud.ru/v1` (python `openai`), паттерн `llm_call(structure=...)` — structured output через tools + tool_choice (AIA_01/02). Не langchain_gigachat (ADR-005).

## GIGACHAT_KEY
Курсовой OpenAI-подобный ключ cloud.ru. ✅ Заведён в секреты OpenClaw 01.11 (protected store, kind secret; egress — только foundation-models.api.cloud.ru; SecretRef id `GIGACHAT_KEY`). Для репо — `.env` (+ `.env.example`). Значение из store недоступно модели/чату; смоук-тесты агента — через .env репо. Также в секретах: CLOUD_RU_API_KEY (тот же хост — проверить GigaChat-доступ на Фазе 1), TAVILY_API_KEY (для search_sdd_docs, ADR-006).

## FastAPI-хребет
Один процесс: REST-эндпоинты (критерий №6) + MCP-эндпоинт `/mcp` (фаза 3). См. ADR-001.

## MCP (Model Context Protocol)
Протокол вызова инструментов тренера из OpenClaw. Транспорт: Streamable HTTP (`FastMCP.streamable_http_app()` → `app.mount("/mcp")` — API подтверждён локально 01.11); stdio — fallback.

## FastMCP
Класс из python `mcp` SDK; отдаёт ASGI-app для монтирования в FastAPI. Установлен локально.

## OpenClaw
Инфраструктура доставки: Telegram-канал + Dashboards (Control UI). Тренер не строит свой бот/UI (ADR-004). Регистрация MCP: `mcp.servers` (url или command+args — подтверждено config-extensions.md).

## Skill (навык OpenClaw)
SKILL.md для агента OpenClaw: когда/как вызывать MCP-инструменты тренера. `sdd-trainer-skill` — привязка к агенту (open question).

## Сессия (OpenClaw)
Изолированный контекст модели, sessionKey. Источник №2 пассивной оценки (OpenSpec-диалоги project-c-agent — существуют, проверено sessions_search).

## Критерии курса (6 обязательных)
1 GigaChat · 2 LangGraph · 3 ≥2 tools внешних API · 4 состояние/memory · 5 роутинг ≥3 путей · 6 FastAPI. Опциональные: поиск, метрики. Сдача: git.standard-data.ru, main, скринкаст ≤10 мин, дедлайн 13.11.2026.

## Relationships
- Граф тренера использует GigaChat через OpenAI-совместимый API cloud.ru (ADR-005)
- Routing node калибруется пассивной оценкой (domain scores)
- FastAPI хостит REST + MCP (ADR-001); консоль — тот же граф без HTTP
- Change proposal фазы N создаётся до кода фазы N (ADR-003)
- OpenClaw-агент вызывает тренера по MCP; тренер не знает про Telegram (ADR-004)
