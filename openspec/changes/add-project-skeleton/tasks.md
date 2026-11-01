# Tasks: Add Project Skeleton (Phase 0)

## 1. Repository
- [x] 1.1 Create local repo `/home/kap/projects/sdd-trainer`, branch `main`
- [x] 1.2 Copy `CONTEXT.md` and `DECISIONS.md` into the repo root

## 2. Package skeleton
- [x] 2.1 Create `src/sdd_trainer/` with module stubs: `__main__`, `models`,
      `token_counter`, `logging_utils`
- [x] 2.2 Create `core/` stubs: `llm_manager`, `graph`, `tools`, `memory`
- [x] 2.3 Create transport packages: `lessons/`, `console/`, `api/`, `mcp/`
- [x] 2.4 Implement `config.py`: `GigaChatConfig` (ADR-005) +
      `TrainerConfig` (ADR-008)

## 3. Infrastructure
- [x] 3.1 `requirements.txt`, `setup.py`, `pytest.ini`, `.coveragerc`,
      `.env.example`, `.gitignore`
- [x] 3.2 `app.py`, `Makefile`, `Dockerfile`, `docker-compose.yml`
- [x] 3.3 CI: `.github/workflows/tests.yml` adapted to the src-layout

## 4. Docs & meta
- [x] 4.1 `README.md` (EN brief), `README_RU.md` (main), `CHANGELOG.md`
- [x] 4.2 `prompts/` (README), `data/`, `docs/`, `backlog/` (BKL convention +
      template)
- [x] 4.3 `openspec init` in the repo root
- [x] 4.4 This change proposal: `proposal.md`, `design.md`, `tasks.md`,
      spec delta

## 5. Verification
- [x] 5.1 Unit tests green locally (config + import smoke), coverage
      threshold set
- [x] 5.2 `openspec validate add-project-skeleton` passes
- [x] 5.3 `.env` is NOT created or committed; `.env.example` has no secret
      values
- [x] 5.4 Private GitHub repo `Alex-Kul777/sdd-trainer` created and pushed
