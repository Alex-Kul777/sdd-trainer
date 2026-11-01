# Design: Add Console Trainer (Phase 1)

Ключевые решения зафиксированы в ADRs (обязательны, конфликт = ошибка):

- ADR-005: GigaChat через OpenAI-совместимый API cloud.ru (не
  langchain_gigachat); structured output через tools + tool_choice
- ADR-006: поиск через Tavily (секрет TAVILY_API_KEY)
- ADR-008: SqliteSaver + thread_id ученика; training-state.json
- ADR-009: контент — markdown-скелеты уроков + JSON-квизы с эталонами

Архитектурный шаблон — роутинг-агент курса (AIA_06): assess → route →
teach/quiz.

Тестовый шов (сверено с владельцем 01.11): единственный шов — граница
графа. Unit: FakeLLM, ассерты на внешнее поведение (маршрут, чекпоинт,
training-state, F1). Integration: тот же шов с реальным GigaChat, skip без
GIGACHAT_KEY. Консоль — тонкий клей без бизнес-логики, ручной смоук.

Спека фичи: GitHub Issue #1.
