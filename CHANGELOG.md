# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **FastAPI HTTP transport (PSA-T2, issue #13)**: one FastAPI process now serves REST (`GET /health`, `POST /sessions/{student}/start`, `POST /sessions/{student}/answer`, `GET /sessions/{student}/stream` — SSE with human-in-the-loop) and mounts the MCP Streamable HTTP endpoint at `/mcp` via `FastMCP.streamable_http_app()` — ADR-001 honoured literally; stdio remains the fallback (ADR-010); REST payloads match the MCP tools byte-for-byte (pinned by test).
- **get_student_history (PSA-T3, issue #14)**: the trainer pulls the student's dialogue history itself via `openclaw sessions --json` (subprocess, defensive parsing, graceful degradation to an empty result with a note — ADR-007 honoured).

### Changed
- **LESSON_DOMAINS now lists reality (PSA-T4, issue #15)**: the constant holds only `openspec-basics` — the single domain with authored content; the six roadmap domains moved to `docs/roadmap.md` (Phase 3 curriculum).
- **ADR-010 promoted to DECISIONS.md (PSA-T1)**: the MCP-over-FastMCP/stdio decision now lives in the single-file ADR home, completing the `add-mcp-integration` archival.

### Added
- **Teach node T4 (issue #5)**: the lesson skeleton
  `prompts/lessons/openspec-basics.md` (ADR-009 sections: Goal / Key
  concepts / Socratic questions / Examples / Quiz ref) with a validating
  loader (a skeleton missing sections fails loudly); `search_sdd_docs` —
  the Tavily client tool (ADR-006, task 2.3): POST `/search` with the
  bearer key, results as `{title, url, content}`; the teach node (task 3.3)
  unfolds the skeleton into a real lesson under the assessed level
  (`state["assessment"]["level"]` from T3; new_topic / partial / knows_it
  directives), asking through a structured `DocsDecision` whether the
  skeleton suffices and pulling fresh docs via `search_sdd_docs` on demand
  — the tool call and its results land in the session log; a search outage
  degrades to a skeleton-only lesson (exception type only in the log), and
  a DocsDecision without a query falls back to a deterministic domain
  default (live-model defect found by the demo, fixed test-first);
  `LLMManager.complete()` — plain prose completion for the lesson (no
  tools, no history, same reasoning-model fallback); unit tests at the
  graph seam (fake LLM + fake docs search, no network) and live
  integration tests (real GigaChat lesson + real Tavily search; Tavily is
  geo-blocked from this host's IP — 403 at the WAF level even without
  credentials — so live runs go through the host's existing local proxy
  via the standard `HTTPS_PROXY` env var, no code changes)
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
