# Smoke Checklist — Course Criteria 1–5 in One Pass (issue #8, task 7.3)

Manual smoke for the Phase 1 slice (`add-console-trainer`): one pass of the
console trainer where **all five course criteria are visible in the session
logs**. This is also the scenario for the submission screencast (mini-round 4).

Preconditions:

- `.env` at the repo root with `GIGACHAT_KEY` (and `TAVILY_API_KEY` for the
  docs tool) — loaded automatically by `config.py`, never printed, never
  committed (`.gitignore`).
- Interpreter: `.venv/bin/python` (repo venv).
- Tavily is geo-blocked from this host: run everything with
  `HTTPS_PROXY=http://127.0.0.1:7890` (mihomo split tunnel — only the blocked
  domain goes through the VPN, GigaChat/cloud.ru goes direct).
- Routing scenarios use **fresh student names** — the checkpointer keys state
  by thread id `student:<name>` (ADR-008), so a name reuse would resume an old
  checkpoint instead of starting a new session.

## Criteria → evidence map

What exactly to look for in the session log, per criterion:

| # | Course criterion | Where it is visible |
|---|------------------|---------------------|
| 1 | GigaChat via the OpenAI-compatible API (ADR-005) | Session header: `Модель: <model> · endpoint: <base_url> (ADR-005)`; every structured decision (assessment, route) is a live LLM call with tools + tool_choice; `--assess` demo prints the parsed `Assessment` JSON |
| 2 | LangGraph graph | The session **is** the graph: `[граф]`-prefixed log lines flow `assess → route → (clarify → route) → teach → quiz → END`, driven by conditional edges; the unit suite builds the same graph with a FakeLLM at the seam |
| 3 | ≥ 2 external tools | (a) `Инструмент analyze_student_repo("<path>"): <summary>` — assess node log line, requires `--repo-path`; (b) `Инструмент search_sdd_docs("<query>"): N результат(ов) — …` — teach node log line, only when the model decides the skeleton is insufficient (see honest note below) |
| 4 | Memory / checkpoint | Interrupt a session (Ctrl-D at any question): `[чекпоинт] Сеанс прерван — состояние сохранено в чекпоинте.`; restart with the same `--student`: `[чекпоинт] Найден незавершённый сеанс — возобновляю с чекпоинта (критерий 4).` + `[чекпоинт] История ученика (из чекпоинта):`; `data/checkpoints.sqlite` + `data/training-state.json` (score, streak) persist across restarts |
| 5 | Routing with ≥ 3 paths | Log line `Маршрут: <path> — <reason>` with `path` ∈ {`knows_it`, `partial`, `new_topic`, `clarification`}; the smoke pass demonstrates ≥ 3 different paths across runs |

### Honest note on `search_sdd_docs` (criterion 3b)

The teach node asks GigaChat whether the lesson skeleton is sufficient; only a
"needs fresh docs" decision calls Tavily. **The code is not bent to force a
demo.** In the 2026-11-03 smoke pass the live model requested fresh docs in
most sessions, so the tool fired repeatedly in the main session log (Runs 1,
2a, 2b, 4). If a given run does not trigger it, the second tool is still
proven live by
`tests/integration/test_tools_live.py::test_search_sdd_docs_returns_real_results_live`
(a real Tavily call, skipped without `TAVILY_API_KEY`).

## Smoke pass procedure (one pass = the run series below)

Piped input feeds the HITL interrupts in order (calibration answer, then quiz
answers); exhausting stdin = Ctrl-D = an interrupted session, which is exactly
what Run 2 needs.

### Run 1 — main session: `partial` path + repo tool (criteria 1, 2, 3a, 5)

```bash
HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python -m sdd_trainer \
  --session --student smoke1 --repo-path /home/kap/projects/sdd-trainer
```

Calibration answer: mid-level (knows what `specs/`/`changes/` are, unsure
about change-proposal anatomy). Expected flow: `analyze_student_repo` log line
→ assessment → `Маршрут: partial …` → lesson → 5 quiz answers → end summary
with `Прогресс (training-state.json): счёт …, серия …` and `Что дальше: …`.

### Run 2 — interrupt + resume from the checkpoint (criterion 4)

1. Same command with `--student smoke2`; pipe the calibration answer plus
   **two** quiz answers, then EOF → `[чекпоинт] Сеанс прерван …` + summary
   (`Что дальше: сеанс не дошёл до квиза …`).
2. Re-run with the same `--student smoke2`; pipe the remaining quiz answers →
   `[чекпоинт] Найден незавершённый сеанс — возобновляю с чекпоинта
   (критерий 4).` + prior history + quiz continues from the pending question.

### Runs 3–5 — routing variety (criterion 5: ≥ 3 paths total with Run 1)

- **Run 3, `knows_it`** (`--student smoke3`): expert calibration answer →
  `Маршрут: knows_it …` → quiz directly, no lesson.
- **Run 4, `new_topic`** (`--student smoke4`): "совершенно не знаком с темой"
  → `Маршрут: new_topic …` → full lesson from the skeleton.
- **Run 5, `clarification`** (`--student smoke5`): vague, self-contradictory
  answer → assessment confidence < 0.5 → `Маршрут: clarification —
  уверенность … ниже порога …` → a clarifying question (EOF is fine here).

The `clarification` path is deterministic below the confidence threshold
(0.5, up to 2 rounds); the other three are GigaChat's structured
`RouteDecision` (ADR-005). Runs 3–5 may be truncated after the route/lesson
evidence is on screen — only Run 1 and Run 2 must complete.

## Screencast scenario (submission video, in order)

0. Optional, for a clean demo: delete the runtime artifacts first —
   `data/training-state.json` + `data/checkpoints.sqlite` (both git-ignored;
   training-state is per-domain and accumulates across every session and test
   run on the machine, so a fresh file makes the on-screen numbers
   unambiguous).
1. Repo tour (30 s): tree, `DECISIONS.md` ADR list, `data/quizzes/` +
   lesson skeleton — what is authored vs runtime.
2. Run 1 in full (criteria 1, 2, 3a + 3b, 5-`partial`, end summary with the
   training-state score and "Что дальше").
3. Run 2 both halves (criterion 4): interrupt mid-quiz → restart → the
   `Найден незавершённый сеанс — возобновляю с чекпоинта` banner + prior
   history + the quiz continues from the pending question.
4. Runs 3–5, fast-forwarded to each `Маршрут: …` line (criterion 5: three+
   paths shown).
5. Open `data/training-state.json` (score/streak persisted) and point at
   `data/checkpoints.sqlite`.
6. If `search_sdd_docs` never fired on camera: run the live Tavily test
   (criterion 3b) and say so honestly.

## Live pass log — 2026-11-03

Actual run evidence; quotes are verbatim session-log lines. Full transcripts:
`/tmp/sdd-smoke/run*.log` (ephemeral, not committed).

- **Run 1 (`smoke1`, partial, `--repo-path`):** header `Модель:
  GigaChat/GigaChat-3-Pro · endpoint: https://foundation-models.api.cloud.ru/v1
  (ADR-005)` (criterion 1); `Инструмент analyze_student_repo("/home/kap/projects/
  sdd-trainer"): openspec/ активен: активные changes — add-console-trainer,
  add-project-skeleton; требований SHALL — 11; сценариев WHEN/THEN — 9`
  (criterion 3a); `Маршрут: partial — …` (criterion 5); `Инструмент
  search_sdd_docs("OpenSpec change proposal workflow and anatomy official
  documentation"): 5 результат(ов) — …` (criterion 3b); `Урок готов: скелет
  openspec-basics развёрнут под уровень partial`; quiz 5 вопросов, F1
  0.38/0.35/0.37/0.35/0.19 → `Квиз не зачтён: 0.33 (порог 0.60)`; summary:
  `Прогресс (training-state.json): счёт 0.33, серия 0, уроков завершено 2` +
  `Что дальше: квиз не зачтён — перечитай урок выше и перезапусти сеанс с тем
  же --student, чтобы пройти квиз снова`.
- **Run 2 (`smoke2`, checkpoint) — exposed a real bug, then proved the fix:**
  - 2a: calibration + two quiz answers, EOF at q3 → `[чекпоинт] Сеанс
    прерван — состояние сохранено в чекпоинте.` + summary `Что дальше: сеанс
    не дошёл до квиза — продолжи с тем же --student`.
  - 2b: restart did **not** resume — the gate `if snapshot.next:` missed the
    mid-quiz pause (LangGraph leaves `snapshot.next` empty after the first
    resume cycle while the task still holds a pending interrupt), so a fresh
    session started silently. Fixed TDD-first: new pure helper
    `has_pending_session(snapshot)` + 4 unit tests (commit `4551f0f`).
  - 2c (fixed console, same `--student smoke2`): `[чекпоинт] Найден
    незавершённый сеанс — возобновляю с чекпоинта (критерий 4).` +
    `[чекпоинт] История ученика (из чекпоинта):` → quiz resumed from the
    pending q3 and completed: F1 q1–q5, `Квиз не зачтён: 0.25 (порог 0.60)`,
    `Прогресс (training-state.json): openspec-basics — счёт 0.25, серия 0,
    уроков завершено 2` (criterion 4).
- **Run 3 (`smoke3`, knows_it):** `Маршрут: knows_it — Ученик демонстрирует
  уверенное и правильное понимание темы OpenSpec basics … Нет необходимости в
  лекции; сразу подходит квиз.` → quiz q1 directly, no lesson (criterion 5).
- **Run 4 (`smoke4`, new_topic):** `Маршрут: new_topic — Занятие полностью
  новое для ученика … требуется полный базовый урок.` → `Инструмент
  search_sdd_docs("OpenSpec Spec-Driven Development basics tutorial
  introduction"): 5 результат(ов) — …` → `Урок готов: скелет openspec-basics
  развёрнут под уровень new_topic` → quiz q1 (criterion 5).
- **Run 5 (`smoke5`/`smoke6`, clarification — honest miss):** two attempts to
  elicit confidence < 0.5; the live model stayed confident both times
  (`Оценка: new_topic (уверенность 0.85)`, then `Оценка: partial
  (уверенность 0.80)`). The clarification path is deterministic below the
  0.5 threshold and is covered by unit tests
  (`test_low_confidence_routes_to_clarification_without_llm_call`,
  `test_clarification_round_reassesses_and_routes` in
  `tests/unit/test_graph.py`). Criterion 5 needs ≥ 3 paths — met live by
  `partial` / `knows_it` / `new_topic`.
- **`search_sdd_docs`:** fired in Runs 1, 2a, 2b and 4 (real Tavily results
  through the mihomo split tunnel, `HTTPS_PROXY=http://127.0.0.1:7890`) —
  criterion 3b demonstrated in the main session, no fallback needed.

Verdict: **all five criteria visible in the live session logs.** Criterion 4
was demonstrated the hard way: the smoke exposed a real mid-quiz resume bug,
fixed with TDD, and the fixed console resumed correctly. The ADR-005 fallback
to the reasoning model was not exercised live (the primary model never
failed); it is covered by the `llm_manager` unit tests.
