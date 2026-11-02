# OpenSpec-основы (openspec-basics)

Скелет урока домена `openspec-basics` — фаза 1, change `add-console-trainer`
(ADR-009: фиксированные секции = стабильный контракт развёртки). GigaChat
разворачивает скелет в полный урок под уровень ученика: new_topic — полный
урок с нуля, partial — разбор пробелов, knows_it — краткий рекап.

## Goal

После урока ученик умеет:

- объяснить, что такое Spec-Driven Development и почему источник истины —
  спецификация, а не код;
- назвать структуру `openspec/` в репозитории: `specs/` (стабильные
  спецификации) и `changes/` (change proposals);
- прочитать требование: `### Requirement:` с **SHALL** и `#### Scenario:` с
  **WHEN/THEN**;
- описать анатомию change proposal: proposal.md (зачем) → design.md (как) →
  tasks.md (чек-лист) → дельта спеки (ADDED/MODIFIED);
- описать цикл работы: explore → propose → apply → archive;
- узнать живой пример: сам тренер построен по этому процессу (change
  `add-console-trainer` в этом же репозитории).

## Key concepts

- **SDD (Spec-Driven Development)** — методология: спецификация — источник
  истины, план до кода. Код меняется вместе с требованиями, спека остаётся
  контрактом, с которым сверяется каждая строчка.
- **OpenSpec** — инструмент SDD: структура `openspec/` в репозитории + CLI
  (`openspec`, v1.14.0). Не фреймворк кода, а фреймворк требований.
- **Спецификация** — `openspec/specs/<capability>/spec.md`: `## Purpose` +
  `### Requirement:` (инвариант с **SHALL**) + `#### Scenario:`
  (**WHEN** … **THEN** …). Описывает «как есть» — текущее, проверенное
  поведение.
- **Change proposal** — `openspec/changes/<kebab-case>/`: `proposal.md`
  (проблема и решение, scope), `design.md` (ключевые решения, ссылки на
  ADR), `tasks.md` (чек-лист реализации), `specs/` (дельта требований:
  ADDED / MODIFIED). Единица работы мета-процесса: 1 фаза проекта = 1
  change (ADR-003).
- **specs/ против changes/**: specs/ — истина «как есть», changes/ —
  предложение «как будет». После review и apply дельта переносится в
  specs/, а change уходит в `changes/archive/`.
- **Зачем строгий формат**: Requirement с SHALL задаёт инвариант, Scenario с
  WHEN/THEN — проверяемый пример; по такой спеке можно писать тесты и
  валидировать изменения (`openspec validate`).

## Socratic questions

- Если код «всегда прав» о себе, почему источником истины объявляют спеку,
  а не код?
- Что не так с требованием без SHALL и сценарием без WHEN/THEN — и почему
  формат делают настолько строгим?
- Зачем в change proposal дельта спеки, если есть tasks.md? Что из них
  переживёт архивацию и останется в specs/?
- Что случится с папкой `changes/add-console-trainer/` после apply? Где
  будет жить её дельта?

## Examples

- Требование из спеки этого репозитория (capability `console-trainer`):

  ```
  ### Requirement: Routing With At Least Three Paths
  The routing node SHALL select between `knows_it`, `partial`, and
  `new_topic` paths, plus `clarification` when the assessment is
  inconclusive.

  #### Scenario: Route selected by assessment
  WHEN the assess node produces a level for the domain
  THEN the route node selects exactly one path and the selection is
  visible in the session log
  ```

- Живой change proposal этого репозитория — `add-console-trainer`:
  `proposal.md` (проблема: скелет без поведения; решение: вертикальный срез
  тренера), `design.md` (ссылки на ADR-005/006/008/009, тестовый шов),
  `tasks.md` (7 групп задач с чекбоксами), `specs/console-trainer/spec.md`
  (дельта ADDED).

- Цикл на практике: explore (читаем specs/, понимаем текущее поведение) →
  propose (новый change с дельтой) → apply (коммиты по tasks.md, дельта
  переносится в specs/) → archive (change в `changes/archive/`).

## Quiz ref

- Квиз домена: `data/quizzes/openspec-basics.json` (создаётся в T5,
  issue #6): вопросы, эталонные ответы, веса для F1.
- Урок готовит ученика к квизу: ключевые факты (структура openspec/,
  SHALL/WHEN/THEN, анатомия и цикл change proposal) — кандидаты в вопросы.
