# Screencast Scenario — MCP Prototype (issue #11, task 3.2)

> **Status: CLOSED — superseded by the defense screencast video**
> (2026-11-05). The live-console demo this scenario describes was recorded
> as an animated terminal inside the defense presentation video:
> `docs/presentation/defense-screencast/sdd_trainer_defense_screencast_HQ.mp4`
> (slide 6 «Живой сеанс в консоли», built from the real session logs of
> 2026-11-05). This document is kept as the underlying scenario and the
> gotchas reference; no separate recording is planned.

Step-by-step recording scenario for the submission video of the Phase 2
prototype: the SDD trainer driven by an MCP client over stdio. Modeled on
the Phase 1 screencast scenario (inside
[smoke-checklist.md](smoke-checklist.md)); every frame below was dry-run
live on 2026-11-03 (evidence: the live pass log in
[mcp-smoke-checklist.md](mcp-smoke-checklist.md)). Target length: **6–8
minutes**. Bracketed numbers are the course criteria each frame proves.

## Preconditions — gotchas from the M2 verification

- **(a) `knows_it` skips the lesson.** The demo client's default calibration
  answer is the expert one → `Маршрут: knows_it` → quiz directly, no lesson.
  For the with-lesson take (frame 3) pass the **weaker mid-level answer**
  (`--answer "Видел проект с OpenSpec: … не разбирал, на практике не
  применял."` — the exact text is in the smoke checklist, Run A) →
  `partial` → lesson → quiz.
- **(b) Tavily is geo-blocked from this host.** Every command runs with
  `HTTPS_PROXY=http://127.0.0.1:7890` (mihomo split tunnel: only the blocked
  domain goes through the VPN, GigaChat/cloud.ru goes direct). Without it a
  live `search_docs` fails with a network error — show the proxy prefix in
  the on-screen commands, it is part of the story.
- **(c) Demo quiz answers are the authorial references**
  (`data/quizzes/openspec-basics.json`, loaded by `scripts/mcp_demo.py`) —
  the weighted token F1 vs the reference is 1.00, so the pass verdict
  reproduces take after take (ADR-009: deterministic F1, no LLM judge). A
  real student answering in their own words gets an honest score.
- **(d) The server's stdout is the MCP protocol.** Never show
  `python -m sdd_trainer.mcp` expecting output — it waits silently on stdin
  (that silence is frame 2's point). The **client** prints the whole
  transcript; the server's httpx request logs go to stderr.
- **(e) The restart frame needs the probe snippet.** The demo client cannot
  resume a mid-quiz session (its fixed script calls `answer_calibration`
  after `start_session`; the server's state-machine guard correctly rejects
  that). Save the probe from
  [mcp-smoke-checklist.md](mcp-smoke-checklist.md) to `/tmp/mcp_probe.py`
  before recording — frames 4 and 5 use it.
- **(f) Fresh state and fresh names.** Step 0 (frame 0) deletes the runtime
  artifacts so the progress numbers are unambiguous; every take uses a
  fresh `--student` (thread id `student:<name>`, ADR-008 — a name reuse
  resumes an old checkpoint).

## Recording plan (frames, in order)

1. **Clean slate (15 s).** `rm data/checkpoints.sqlite
   data/training-state.json` (git-ignored runtime artifacts); show `data/`
   now holding only `quizzes/` + `.gitkeep` — authored content vs runtime.
2. **Repo tour (30–40 s).** `tree -L 2` (or `ls`); scroll `DECISIONS.md`
   (ADR-001…010 — say: decisions 005 GigaChat, 008 checkpointing, 009 quiz
   format, 010 MCP stdio); open `openspec/changes/add-mcp-integration/`
   (proposal/design/tasks — the change is developed per ADR-003); point at
   `src/sdd_trainer/mcp/server.py` + `scripts/mcp_demo.py` — "the server is
   a thin wrapper over the Phase 1 graph; the client is the auto-demo".
3. **The transport, visually (20–30 s) [6].** Terminal: `python -m
   sdd_trainer.mcp` — it sits **silent**, waiting for the MCP protocol on
   stdin (stdio transport, ADR-010). Ctrl-C. Then the client side of the
   handshake: `/tmp/mcp_probe.py --student sc --list-tools` → `Инструменты:
   analyze_repo, answer_calibration, answer_clarification,
   answer_quiz_question, get_progress, search_docs, start_session` — seven
   tools over a real subprocess.
4. **Full session with lesson (2.5–3 min) [1, 2, 5, 6].** The demo with the
   **weaker** answer (gotcha a), fresh student:

   ```bash
   HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python scripts/mcp_demo.py \
     --student sc-demo1 --answer "<mid-level answer from the checklist Run A>"
   ```

   On screen, in order: the client header (`Сервер: python -m sdd_trainer.mcp
   (stdio, ADR-010)`); the calibration question; the live verdict
   (`Уровень: partial / Уверенность: 0.7` — a real GigaChat structured call,
   criterion 1); `Маршрут: partial` (criterion 5); the unfolded lesson
   (criterion 2 — the graph ran assess → route → teach); five quiz
   questions answered with the references (gotcha c); `Счёт: 1.00 (порог
   0.60) / Итог: зачтён`; `Прогресс (training-state)`. Voiceover: each tool
   call = one graph step to the next interrupt (ADR-010).
5. **Direct tools (40 s) [3].** With the proxy prefix visible (gotcha b):

   ```bash
   HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python /tmp/mcp_probe.py \
     --student sc-tools --analyze /home/kap/projects/sdd-trainer \
     --search "OpenSpec spec driven development change proposal workflow"
   ```

   `RepoAnalysis: practice=True` + the summary line (active changes, SHALL,
   WHEN/THEN counts) — tool 1; `Docs results: 5` — live Tavily results,
   tool 2 (criterion 3). If the lesson in frame 4 already logged
   `Инструмент search_sdd_docs(…)` (the graph's own tool fired), say so —
   that is the same Tavily seam from inside the graph.
5b. **HTTP insert — same core, third entrance (30 s) [6].** In a second
   terminal: `python -m sdd_trainer.app` (uvicorn on localhost:8000), then
   `curl -s localhost:8000/health` and `curl -N "localhost:8000/sessions/<student>/stream"`
   — the lesson streams over SSE while the terminal shows `event: node` lines
   (assess → route → teach). Point at the `/mcp` mount note in the startup
   log: "the same FastAPI process also serves MCP over Streamable HTTP —
   ADR-001 literally; stdio is the fallback". Ctrl-C the server.

6. **THE RESTART — the strongest frame (1.5 min) [4].**
   - Start a session and kill it mid-quiz (client exit kills the stdio
     server subprocess):

     ```bash
     HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python /tmp/mcp_probe.py \
       --student sc-restart --start --calibration "<mid-level answer>" --quiz 2
     ```

     The transcript ends on the pending q3 — two answers given, three to go.
   - Optional beat: `ps aux | grep sdd_trainer.mcp` — no server process
     left. The server is **dead**.
   - A brand-new client + a brand-new server, same student:

     ```bash
     HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python /tmp/mcp_probe.py \
       --student sc-restart --start --quiz 3 --progress
     ```

     On screen: `<<< type=question · resumed=True · kind=quiz` with the very
     q3 → answers → `Вердикт квиза: счёт 1.00, зачтён` → progress. Say it
     plainly: nothing was in memory — the session lived in
     `data/checkpoints.sqlite` (ADR-008), and the new server process picked
     it up mid-quiz.
7. **Routing variety, fast-forwarded (40 s) [5].** Two short takes, cut to
   the `Маршрут:` lines: the demo's default expert answer (`--student
   sc-knows`) → `Маршрут: knows_it` → quiz directly, **no lesson**; and
   `--answer "Совершенно не знаком…"` (`--student sc-new`) → `Маршрут:
   new_topic` → full lesson. Three routes on camera with frame 4
   (criterion 5: ≥ 3 paths).
8. **Closing (30 s) [4, 6].** `/tmp/mcp_probe.py --student sc-close
   --progress` → the domain score/streak; open `data/training-state.json`;
   point at `data/checkpoints.sqlite`. Final slide: criteria 1–6 → one line
   each on where they were shown (the map at the top of
   [mcp-smoke-checklist.md](mcp-smoke-checklist.md)).

## Honest notes for the voiceover

- **Routes and lesson prose are live model output.** If a take routes
  differently than the script predicts, say so and keep it or retake — the
  graph follows whatever GigaChat decides; nothing is hard-coded. (All
  frames above reproduced as scripted in the 2026-11-03 dry run.)
- **The teach node's fresh-docs search is model-driven.** If it does not
  fire on camera, criterion 3b is still proven live by the direct
  `search_docs` call in frame 5 — say that honestly instead of forcing it.
- **The `clarification` route** is deterministic below 0.5 confidence and
  unit-covered; the live model routes confidently (Phase 1 tried twice to
  elicit it and failed) — do not burn recording time on it.
- **The quiz verdict is deterministic** (F1 vs authorial references,
  ADR-009) — the 1.00 passes are reproducible, not staged luck; a real
  student's own words would get an honest score.
- **Progress is per-domain, not per-student** (ADR-008): the counter
  accumulates across every passed session on the machine — frame 1's clean
  slate is what makes the on-screen numbers unambiguous.

## Dry-run log — 2026-11-03

The full scenario was executed live on 2026-11-03 (fresh runtime artifacts,
fresh students `mcp-smoke1..7`): frames 4–7 ran verbatim (routes `partial` /
`knows_it` / `new_topic`, deterministic 1.00 quiz passes, live Tavily
through the split tunnel, mid-quiz kill → `resumed=True` → completed quiz),
and every run exited 0. Verbatim quotes and per-run evidence:
[mcp-smoke-checklist.md](mcp-smoke-checklist.md), live pass log
(transcripts: `/tmp/sdd-mcp-smoke/*.log`, ephemeral).
