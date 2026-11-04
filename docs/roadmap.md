# Curriculum Roadmap — Phase 3

`LESSON_DOMAINS` in `src/sdd_trainer/lessons/__init__.py` lists exactly the
domains that have authored content today: `openspec-basics` (ADR-009 skeleton
in `prompts/lessons/` + quiz in `data/quizzes/`). The six domains of the
original plan (PLAN-FINAL-PROJECT.md, section 2) have no content yet — they
are the Phase 3 curriculum roadmap and live here, in docs, not in code
constants (pre-submission review, 04.11, finding 4b).

Each domain below ships only when it has a full content slice: an ADR-009
lesson skeleton and a hybrid-authorship quiz. A domain is added to
`LESSON_DOMAINS` the moment its content lands — the constant must never
advertise domains that do not exist.

| # | Domain | One-line description |
|---|--------|----------------------|
| 1 | `sdd-fundamentals` | Spec as the source of truth; plan before code. |
| 2 | `openspec-structure` | The `specs/` vs `changes/` split of an OpenSpec repo. |
| 3 | `requirement-writing` | SHALL requirements + WHEN/THEN scenarios. |
| 4 | `change-proposals` | The proposal → design → tasks artifact chain. |
| 5 | `openspec-workflow` | The explore → propose → apply → archive lifecycle. |
| 6 | `brownfield-sdd` | Incremental spec-driven changes in a live project. |
