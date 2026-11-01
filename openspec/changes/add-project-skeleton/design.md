# Design: Add Project Skeleton (Phase 0)

## Context

Скелет создаётся до всякой логики: фазы 1–3 наращивают транспорты поверх
одного LangGraph-графа. Поэтому каркас фиксирует границы модулей и конвенции,
но не тащит поведение. Образец структуры — rag_GigaChat (ADR-002); код пишем
свой.

## Decisions

| Решение | Обоснование |
|---------|-------------|
| src-лейаут + `pip install -e .` | ADR-002 (образец); изолирует пакет, работает с coverage и CI |
| `GigaChatConfig`-паттерн (dataclass, креды из env) | ADR-002 + ADR-005: ключ `GIGACHAT_KEY` из env, `base_url` cloud.ru, без langchain_gigachat |
| Модели: `GigaChat/GigaChat-3-Pro` → fallback `GigaChat/GigaChat-3.5-Reasoning` | ADR-005; точный ID fallback проверить `models.list` в фазе 1 |
| Модули core/ — заглушки (docstring + pass), без импортов тяжёлых зависимостей | Фаза 0 не зовёт API; скелет импортируется без установки langgraph/mcp |
| `TrainerConfig`: `data/checkpoints.sqlite`, `thread_id="student:alex"` | ADR-008 (SqliteSaver); sqlite-файл в .gitignore |
| Тесты: unit (config, import-smoke), без сети | Grilling Q12: покрывать критичные пути; смоук с реальным GigaChat — фаза 1 |
| CI без обязательных секретов | Фаза 0 не зовёт API; `GIGACHAT_KEY` пробрасывается опционально (секрет появится в фазе 1) |
| `openspec init` + change-per-phase | ADR-003: 1 фаза = 1 change; propose до кода |
| python-dotenv в requirements | Поддержка паттерна `.env` / `.env.example` (конвенция образца) |
| Приватный репозиторий GitHub | Grilling Q1: приватный `sdd-trainer` (Alex-Kul777) |

## Risks / Trade-offs

- Заглушки не содержат поведения — порог coverage в фазе 0 зафиксирован
  низким (40%), поднимается в фазе 1;
- Приватный репозиторий: бейджи CI/coverage видны только авторизованным —
  сознательно (курсовой проект; публичность решает владелец);
- Версии зависимостей закреплены (pinned) по локально проверенным релизам —
  распаковка конфликтов отложена до фазы 1.
