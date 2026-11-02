# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Trainer graph T3 (issue #4)**: LangGraph graph assess → route →
  teach/quiz (AIA_06 routing-agent template, criterion 2) with routing over
  at least three paths — knows_it / partial / new_topic plus clarification
  on low assessment confidence (criterion 5) — the selected route is
  visible in the session log; SqliteSaver checkpointer under the per-student
  thread id `student:<name>` (ADR-008, criterion 4) — an interrupted session
  resumes from the checkpoint on the next run; console session mode
  `python -m sdd_trainer --session [--student NAME]` (task 6.1): thin
  input/print glue over the graph (interrupt → Command(resume)) with a
  session summary at exit; assessment prompts moved to `core/prompts.py`
  (re-exported from `__main__`, T2 imports keep working); unit tests at the
  graph seam with a fake LLM — routing paths, deterministic clarification
  with a bounded loop, checkpoint resume across a simulated restart — and
  live GigaChat integration tests on the same seam (tasks 3.2/4.1/6.1/7.2;
  teach/quiz are stubs pending T4/T5)
- **Structured output T2 (issue #3)**: `Assessment` schema — level
  (`new_topic`/`partial`/`knows_it`), justification, confidence, domain — and
  the generic `LLMManager.llm_call(messages, structure)`: GigaChat structured
  output via `tools` + `tool_choice` with validation back into the Pydantic
  schema, no free-text parsing (AIA_02, ADR-005); fallback to the reasoning
  model when the primary one fails (tasks 1.2/1.3); `RouteDecision` schema
  (paths fixed by the spec, routing logic is T3, task 2.1); console demo
  `python -m sdd_trainer --assess`; unit tests (FakeOpenAI, no network) and
  live integration tests (skipped without `GIGACHAT_KEY`)
- **Console trainer T1 «прокол» (issue #2)**: `python -m sdd_trainer` — live
  GigaChat dialogue via the OpenAI-compatible cloud.ru API (ADR-005):
  `LLMManager.chat()` with an in-memory history, polite exit
  (q/quit/exit/Ctrl-D), friendly message when `GIGACHAT_KEY` is missing;
  unit tests for the config and the client seam (FakeOpenAI, no network)

### Fixed
- Fallback model ID corrected per live `models.list`:
  `ai-sage/GigaChat3.5-432B-A28B-Reasoning` (add-console-trainer task 1.1)

### Changed
- Renamed `CONTEXT.md` → `GLOSSARY.md` (mattpocock skills convention) and added
  the engineering-skills config: `AGENTS.md` + `docs/agents/` (issue tracker,
  triage labels, domain docs)

## [0.1.0] - 2026-11-01

### Added
- **Project skeleton (phase 0)**: src-layout package `sdd_trainer` with core
  module stubs (`llm_manager`, `graph`, `tools`, `memory`) and transport
  packages (`lessons`, `console`, `api`, `mcp`)
- **Configuration** (ADR-005): `GigaChatConfig` — GigaChat via the
  OpenAI-compatible cloud.ru API (`GigaChat/GigaChat-3-Pro` → fallback
  `GigaChat/GigaChat-3.5-Reasoning`); `TrainerConfig` with SqliteSaver
  persistence paths (ADR-008)
- **Pydantic schemas** (AIA_02): `UserProfile`, `DomainProgress`, `QuizQuestion`,
  `QuizResult`, `LessonPlan`
- **Test layout**: `tests/unit|integration|performance|fixtures` with config
  unit tests and an import smoke test; `pytest.ini` + `.coveragerc`
- **CI**: GitHub Actions workflow (`tests.yml`) adapted to the src-layout
- **Infrastructure**: `Makefile`, `Dockerfile`, `docker-compose.yml`, `app.py`
  entry point, `.env.example` (no secret values)
- **OpenSpec meta-process** (ADR-003): `openspec/` initialized with the
  `add-project-skeleton` change proposal
- **Docs**: `README.md` (EN brief), `README_RU.md` (main), `CONTEXT.md`,
  `DECISIONS.md`, BKL backlog convention
