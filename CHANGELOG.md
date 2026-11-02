# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
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
