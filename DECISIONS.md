# DECISIONS — SDD Trainer

Формат ADR. Нумерация сквозная. Статусы: accepted | superseded | deprecated.
При Фазе 0 переезжает в корень репо sdd-trainer (конвенция drone_interception).

### ADR-001: MCP-эндпоинт монтируется в тот же FastAPI-процесс
Date: 2026-11-01
Status: accepted
Context: Фаза 3 требует MCP для вызова тренера из OpenClaw; критерий №6 требует FastAPI. Опасение с консультации: FastAPI может выглядеть «обёрткой», если MCP делать отдельным сервисом.
Decision: Один FastAPI-процесс: REST + MCP-эндпоинт `/mcp` (Streamable HTTP, `FastMCP.streamable_http_app()` → `app.mount`). stdio — fallback отдельным процессом. В конфиге OpenClaw: `mcp.servers["sdd-trainer"].url`.
Consequences:
  - ✚ Один процесс/порт/граф — два протокола; FastAPI — хребет, не обёртка
  - ✚ OpenClaw подключается по url (подтверждено: docs/gateway/config-extensions.md)
  - ✚ `FastMCP.streamable_http_app()` существует — проверено локально 01.11
  - − Жёсткая связность: падение FastAPI роняет и MCP
  - − Пиновать версию mcp SDK при реализации

### ADR-002: rag_GigaChat — образец структуры, не форк
Date: 2026-11-01
Status: accepted
Context: Нужен зрелый шаблон репозитория; rag_GigaChat (708 файлов, CI, тесты, GigaChat-интеграция) — собственный и проверенный.
Decision: Копируем скелет и конвенции (GigaChatConfig с env-кредами и профилями моделей, лейаут tests, backlog BKL, CI, Docker, README+README_RU), код пишем свой. Не переносим: temp/, root-дебаг-скрипты, .claude/+CLAUDE.md, experiments/, VISUAL_ANALYSIS.txt.
Consequences:
  - ✚ Знакомые конвенции, проверенный CI-паттерн, готовый паттерн GigaChat-конфига
  - ✚ Нет балласта чужой доменной логики (RAG-пайплайн не нужен)
  - − Ручной перенос: часть файлов адаптировать под пакет sdd_trainer

### ADR-003: change-per-phase — разработка самого проекта по OpenSpec
Date: 2026-11-01
Status: accepted
Context: Мета-идея: тренер преподаёт SDD, на чём сам построен. openspec CLI установлен (v1.14.0).
Decision: Каждая фаза роадмапа = change proposal: `add-project-skeleton`, `add-console-trainer`, `add-fastapi-service`, `add-mcp-integration`. Цикл: propose → apply (коммиты со ссылками на tasks.md) → archive.
Consequences:
  - ✚ Живой openspec/ на защите; скринкаст показывает tasks.md ↔ коммиты
  - ✚ Практика SDD для Алекса до старта тренера; рекурсивный вход пассивной оценки
  - − Накладные расходы ~0.5 дня на фазу
  - − Риск писать спеки задним числом — следить за порядком propose→apply

### ADR-004: Доставка через инфраструктуру OpenClaw — без своего Telegram-бота и UI
Date: 2026-11-01
Status: accepted
Context: Тренер должен общаться с учеником в Telegram и показывать граф/прогресс; строить своего бота — лишняя работа вне критериев курса.
Decision: Telegram-канал и Dashboards — стороны OpenClaw; тренер отдаёт только MCP-инструменты и данные. SKILL.md (`sdd-trainer-skill`) учит агента OpenClaw пользоваться тренером.
Consequences:
  - ✚ Ноль работы по ботам/UI/токенам; демо в существующем чате
  - ✚ Виджет прогресса и диаграмма графа в Control UI
  - − Зависимость от агента OpenClaw как посредника
  - − Формат ответов подчинён каналам (Telegram — без markdown-таблиц)

### ADR-005: GigaChat через OpenAI-совместимый API cloud.ru (не langchain_gigachat)
Date: 2026-11-01
Status: accepted
Context: Ноутбук курса (AIA_01/07) использует `OpenAI(api_key=os.environ["GIGACHAT_KEY"], base_url="https://foundation-models.api.cloud.ru/v1")`, модель "GigaChat/GigaChat-3-Pro"; structured output — через tools + tool_choice с Pydantic-схемой. Изначально планировалась интеграция langchain_gigachat (паттерн rag_GigaChat).
Decision: Следовать курсовому паттерну: python-пакет `openai` + base_url cloud.ru + обёртка llm_call(structure=Pydantic). Модели: GigaChat/GigaChat-3-Pro → fallback GigaChat/GigaChat-3.5-Reasoning (точный ID проверить models.list на Фазе 1). Ключ GIGACHAT_KEY: .env репо + секреты OpenClaw.
Consequences:
  - ✚ Знакомо проверяющим (паттерн занятий 1 и 7); меньше зависимостей
  - ✚ Structured output из коробки (tools/tool_choice) — паттерн AIA_02 переиспользуется
  - − Привязка к endpoint cloud.ru; отказ от зрелой langchain-интеграции

### ADR-006: Tavily — существующий секрет TAVILY_API_KEY
Date: 2026-11-01
Status: accepted
Context: Нужен внешний поисковый API для search_sdd_docs; регистрация нового ключа не требуется.
Decision: Использовать TAVILY_API_KEY из секретов OpenClaw (подтверждён 01.11, hosts: api.tavily.com); в репо — .env. GigaSearch — fallback.
Consequences:
  - ✚ Ноль затрат на регистрацию; ключ уже работает в OpenClaw
  - − Значение живёт в двух местах (секреты + .env репо)

### ADR-007: Тренер тянет данные OpenClaw сам (pull), fallback — пуш
Date: 2026-11-01
Status: accepted
Context: get_student_history — направление данных; у OpenClaw есть CLI `openclaw sessions` (проверено 01.11).
Decision: Тренер вызывает `openclaw sessions` subprocess'ом и сам извлекает историю; fallback — агент OpenClaw пушит контекст через MCP-аргументы.
Consequences:
  - ✚ Автономность тренера; сильное демо «агент сам собирает данные об ученике»
  - − Зависимость от формата вывода CLI — пиновать версию OpenClaw, парсить аккуратно

### ADR-008: API-слой по курсовому паттерну + SqliteSaver-персистентность
Date: 2026-11-01
Status: accepted
Context: Раунд 2 grilling (Q8, Q9). Курс AIA_07 учит /invoke + /stream (ndjson) + /resume (interrupt/Command/thread_id) с InMemorySaver; критерий 4 требует память.
Decision: Эндпоинты: POST /lesson, POST /lesson/stream (ndjson), POST /quiz/resume, GET /progress, GET /health — внутри курсовой паттерн. Чекпоинтер: SqliteSaver (langgraph-checkpoint-sqlite), data/checkpoints.sqlite, thread_id="student:alex"; InMemorySaver — только в unit-тестах.
Consequences:
  - ✚ Знакомый проверяющим API-паттерн; прогресс переживает рестарт сервера
  - ✚ HITL-квизы работают через /quiz/resume с тем же thread_id
  - − Ещё одна зависимость (langgraph-checkpoint-sqlite); sqlite-файл в .gitignore

### ADR-009: Lesson content — markdown skeletons + JSON quizzes
Date: 2026-11-01
Status: accepted
Context: Q10 (раунд 2 grilling): гибридное авторство — скелеты уроков и квизы с эталонами пишутся заранее, GigaChat разворачивает скелет под уровень ученика. Мини-раунд 3 зафиксировал первый срез: домен «OpenSpec основы». Нужен формат контент-файлов.
Decision: Скелеты уроков — markdown в prompts/lessons/<domain>.md с фиксированными секциями (Goal / Key concepts / Socratic questions / Examples / Quiz ref). Квизы — JSON в data/quizzes/<domain>.json: вопросы, эталонные ответы, веса для F1.
Consequences:
  - ✚ Markdown читается и агенту, и человеку: грепается, диффается, правится без кода
  - ✚ Фиксированные секции = стабильный контракт развёртки для llm_manager
  - ✚ Эталоны в JSON = воспроизводимый F1 + structured output через tools/tool_choice (ADR-005)
  - − Два формата (md + json) вместо одного; контракт секций нужно валидировать

### ADR-010: MCP через официальный Python SDK (FastMCP, stdio)
Date: 2026-11-02
Status: accepted
Context: Преподаватель (консультация №1): главное — работающий прототип, код вторичен. mcp==1.27.1 запинен в requirements.txt; FastMCP импортируется (Python 3.12). ADR-001 упоминал MCP-транспорт.
Decision: MCP-сервер строится на FastMCP из официального SDK, транспорт stdio (стандарт локальных MCP-серверов). Декораторный стиль — минимальные обёртки; ядро (граф, tools, память) не переписывается. Инструменты сессии не гоняют граф целиком: каждый вызов возобновляет чекпоинченный граф (ADR-008, thread_id = student) с последним ответом ученика и собирает события до следующего interrupt.
Consequences:
  - ✚ Минимальный код обёрток; интерактивное демо и рестарт-устойчивость бесплатно (ADR-008)
  - ✚ Пошаговое возобновление = одно ядро, два интерфейса (консоль Фазы 1 + MCP Фазы 2)
  - − Свой JSON-RPC поверх stdio отклонён (код вторичен); HTTP/SSE-транспорт отклонён — нужен сервер-процесс и порт для локального демо
  - Продвинуто из archive/2026-11-03-add-mcp-integration/design.md при архивации; в DECISIONS.md перенесён 2026-11-04 (находка ревью — шаг был пропущен)
