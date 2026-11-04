# MCP Smoke Checklist — Course Criteria 1–6 in One Pass (issue #11, task 3.1)

Manual smoke for the Phase 2 slice (`add-mcp-integration`): one pass of the
trainer **driven by an MCP client over stdio** where all six course criteria
are visible in the client transcript. The Phase 1 pass
([smoke-checklist.md](smoke-checklist.md)) proved criteria 1–5 through the
console entry; this pass proves the same graph through the MCP layer
(ADR-010) plus the new criterion 6. It is also the scenario behind the
submission screencast ([screencast-mcp.md](screencast-mcp.md)).

Preconditions:

- `.env` at the repo root with `GIGACHAT_KEY` (and `TAVILY_API_KEY` for the
  docs tool) — loaded automatically by `config.py`, never printed, never
  committed (`.gitignore`).
- Interpreter: `.venv/bin/python` (repo venv).
- Tavily is geo-blocked from this host: run everything with
  `HTTPS_PROXY=http://127.0.0.1:7890` (mihomo split tunnel — only the blocked
  domain goes through the VPN, GigaChat/cloud.ru goes direct; the demo client
  forwards the proxy variables to the server subprocess).
- Routing scenarios use **fresh student names** — the checkpointer keys state
  by thread id `student:<name>` (ADR-008), so a name reuse would resume an old
  checkpoint instead of starting a new session.
- **stdout discipline:** the server's stdout is the MCP protocol stream
  (ADR-010). Never run `python -m sdd_trainer.mcp` bare expecting a transcript
  — it waits silently on stdin. The **client** (demo script or the probe
  below) prints the whole transcript; the server's own lines (httpx request
  logs) go to stderr.

## Criteria → evidence map

What exactly to look for in the client transcript, per criterion:

| # | Course criterion | Where it is visible |
|---|------------------|---------------------|
| 1 | GigaChat via the OpenAI-compatible API (ADR-005) | Every verdict is a live structured call: the transcript's `Вердикт: level=… confidence=…` and `Маршрут: <path> — <reason>` lines come from the model's `Assessment`/`RouteDecision` tool calls; the server's stderr shows one `HTTP Request: POST https://foundation-models.api.cloud.ru/v1/chat/completions "HTTP/1.1 200 OK"` per call. The MCP layer prints no model header (that was console glue) — the endpoint is visible in the stderr httpx lines and `config.py` (ADR-005) |
| 2 | LangGraph graph | The session **is** the checkpointed graph, driven stepwise: each tool call resumes the graph with one answer and stops at the next `interrupt` (ADR-010: один вызов = один шаг графа). The payload's session log shows the node flow `Оценка → Маршрут → Материалы → Урок готов → Проверка знаний → Вопрос qN → Квиз зачтён`; the unit suite builds the same graph with a FakeLLM at the seam |
| 3 | ≥ 2 external tools | (a) `analyze_repo(path)` — direct MCP tool, returns the structured `RepoAnalysis` (summary line with active changes / SHALL / WHEN-THEN counts); (b) `search_docs(query)` — direct MCP tool, live Tavily results (ADR-006, needs the proxy); (c) the graph's own tools fire **inside** sessions: `Инструмент search_sdd_docs("…"): N результат(ов) — …` in the session log when the teach node decides fresh docs are needed (fired live in Run B below). The assess node's internal `analyze_student_repo` needs `repo_path` on `start_session` — the demo client does not pass it; over MCP the passive scan is exercised through the direct `analyze_repo` tool (a) |
| 4 | Memory / checkpoint | Run B: kill the client mid-quiz (the stdio server subprocess dies with it) → start a **brand-new** client + server → `start_session` returns `resumed=True` plus the pending quiz question → the quiz continues from that question and completes; `data/checkpoints.sqlite` + `data/training-state.json` persist across server processes |
| 5 | Routing with ≥ 3 paths | `Маршрут: <path> — <reason>` with `path` ∈ {`knows_it`, `partial`, `new_topic`, `clarification`}`; the smoke pass demonstrates ≥ 3 different paths across runs (Runs A/B, C, D) |
| 6 | MCP (transport stdio, client-agent) | The client spawns `python -m sdd_trainer.mcp` as a subprocess and speaks the protocol: initialize handshake → `list_tools` → 7 tools (`analyze_repo, answer_calibration, answer_clarification, answer_quiz_question, get_progress, search_docs, start_session`) → `call_tool` per step; the server's stdout stays clean — the client prints the transcript, and any stray server print would corrupt the stream (the stdio integration tests double as this canary). Transport stdio per ADR-010; ADR-001's FastAPI-mount is now implemented too (PSA-T2: `app.mount("/mcp")`, `python -m sdd_trainer.app`; see docs/api.md) — stdio remains the fallback |

## Smoke pass procedure (one pass = the run series below)

### Step 0 — clean runtime artifacts

```bash
rm data/checkpoints.sqlite data/training-state.json
```

Both are git-ignored runtime artifacts. training-state is **per-domain, not
per-student** (ADR-008): the score/streak accumulates across every passed
session on the machine — a fresh file makes the on-screen numbers
unambiguous. Back them up first if you care about the accumulated progress.

### Run A — full session with lesson via the demo client (criteria 1, 2, 5-`partial`, 6)

```bash
HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python scripts/mcp_demo.py \
  --student mcp-smoke1 \
  --answer "Видел проект с OpenSpec: в specs/ лежат стабильные спецификации требований, в changes/ — предложения изменений. Но внутреннее устройство change proposal (proposal.md, design.md, tasks.md, дельты спеки) не разбирал, на практике не применял."
```

The **weaker calibration answer matters**: the demo's default answer is the
expert one, which routes `knows_it` and **skips the lesson** (quiz straight
away). For the with-lesson pass use the mid-level answer above → expected
flow: calibration question → `Вердикт: level=partial` → `Маршрут: partial` →
`=== Урок ===` → 5 quiz questions answered with the authorial references
(deterministic F1 1.00, ADR-009) → `Квиз зачтён` → `=== Прогресс
(training-state) ===`.

### Run B — kill mid-quiz, restart, resume from the checkpoint (criterion 4)

Uses the probe snippet below (the demo client cannot resume a mid-quiz
session — see honest notes).

1. Part 1 — drive the session to mid-quiz and let the client exit (the
   server subprocess dies with it):

```bash
HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python /tmp/mcp_probe.py \
  --student mcp-smoke2 --start \
  --calibration "Видел проект с OpenSpec: в specs/ лежат стабильные спецификации требований, в changes/ — предложения изменений. Но внутреннее устройство change proposal (proposal.md, design.md, tasks.md, дельты спеки) не разбирал, на практике не применял." \
  --quiz 2
```

   Expected: verdict `partial` → lesson → quiz q1, q2 answered → the
   transcript ends on the pending q3 (client exit = the kill).

2. Part 2 — a **brand-new** client and server process, same student:

```bash
HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python /tmp/mcp_probe.py \
  --student mcp-smoke2 --start --quiz 3 --progress
```

   Expected: `<<< type=question · resumed=True · kind=quiz` with the very
   q3 → three more reference answers → `Квиз зачтён: 1.00` → progress. The
   new server process lost nothing: the checkpoint IS the state (ADR-008).

### Runs C–D — routing variety (criterion 5: ≥ 3 paths total with Run A)

- **Run C, `knows_it`** — the demo's default expert answer:

```bash
HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python scripts/mcp_demo.py --student mcp-smoke3
```

  Expected: `Маршрут: knows_it` → quiz q1 directly, **no lesson** → 1.00.
- **Run D, `new_topic`**:

```bash
HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python scripts/mcp_demo.py \
  --student mcp-smoke4 \
  --answer "Совершенно не знаком с OpenSpec и spec-driven development, впервые слышу об этом."
```

  Expected: `Маршрут: new_topic` → full lesson from the skeleton → quiz → 1.00.

### Direct tools + state-machine guard (criteria 3, 6)

```bash
HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python /tmp/mcp_probe.py \
  --student mcp-smoke5 --list-tools \
  --analyze /home/kap/projects/sdd-trainer \
  --search "OpenSpec spec driven development change proposal workflow"

HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python /tmp/mcp_probe.py \
  --student mcp-smoke6 --quiz 1
```

Expected: the 7-tool list; `=== RepoAnalysis: practice=True ===` with the
summary line; `=== Docs results: 5 ===` (live Tavily through the proxy); and
for the guard — `<<< type=error` with `message: Нет незавершённого сеанса —
сначала вызови start_session.` (a client can never feed an answer into a
nonexistent session; the unit suite covers the wrong-kind guard too).

## Probe snippet (save as `/tmp/mcp_probe.py`)

A compact MCP client for Run B and the direct-tool steps — the repo's demo
client (`scripts/mcp_demo.py`) covers full sessions; this probe adds
stop-after-N-answers, resume, and arbitrary direct calls. It is a manual
smoke tool, deliberately not committed (this is a docs ticket).

```python
"""mcp_probe.py — компактный MCP-клиент для смоук-чеклиста (issue #11).

Сохраните вне репо (например, /tmp/mcp_probe.py) — это ручной инструмент
смоука, а не код проекта. Поднимает реальный сервер ``python -m
sdd_trainer.mcp`` по stdio — как любая MCP-хост-программа — и выполняет
действия по флагам, печатая транскрипт на консоль клиента (stdout сервера
принадлежит протоколу и остаётся чистым).

Действия выполняются в порядке перечисления:
  --list-tools         список инструментов сервера (handshake + list_tools)
  --start              start_session (возобновит незавершённый сеанс)
  --calibration TEXT   answer_calibration(TEXT)
  --quiz N             answer_quiz_question × N — эталонные ответы тех самых
                       вопросов (по тексту висящего вопроса; без сеанса —
                       blind-ответ, чтобы увидеть guard-ошибку сервера)
  --analyze PATH       analyze_repo(PATH) — локальное сканирование
  --search QUERY       search_docs(QUERY) — живой Tavily (нужен HTTPS_PROXY)
  --progress           get_progress

Запуск: HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python /tmp/mcp_probe.py \
        --student ИМЯ [действия...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _server_params() -> StdioServerParameters:
    """Субпроцесс сервера: тот же интерпретатор, переменные тренера."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key.startswith(("GIGACHAT_", "TAVILY_", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"))
    }
    return StdioServerParameters(
        command=sys.executable, args=["-m", "sdd_trainer.mcp"], env=env
    )


def _payload(result) -> dict:
    """Разобрать результат вызова инструмента в dict."""
    return json.loads(result.content[0].text)


def _show(p: dict) -> None:
    """Компактный транскрипт одного payload (клиент печатает всё)."""
    extra = []
    if p.get("resumed"):
        extra.append("resumed=True")
    if p.get("question_kind"):
        extra.append(f"kind={p['question_kind']}")
    print(f"\n<<< type={p.get('type')}" + (" · " + " · ".join(extra) if extra else ""))
    if p.get("message"):
        print(f"message: {p['message']}")
    if p.get("question"):
        print(f"[тренер] {p['question']}")
    a = p.get("assessment") or {}
    if a:
        print(f"Вердикт: level={a.get('level')} confidence={a.get('confidence')}")
    r = p.get("route") or {}
    if r:
        print(f"Маршрут: {r.get('path')} — {r.get('reason')}")
    if p.get("lesson"):
        print(f"=== Урок ({len(p['lesson'])} символов) ===")
    q = p.get("quiz") or {}
    if q:
        print(f"=== Вердикт квиза: {q.get('domain')} — счёт {q.get('score', 0.0):.2f} "
              f"(порог 0.60), {'зачтён' if q.get('passed') else 'не зачтён'} ===")
        print(f"  {q.get('feedback')}")
    if p.get("domains"):
        print("=== Прогресс (training-state) ===")
        for domain, entry in sorted(p["domains"].items()):
            print(f"  · {domain}: счёт {entry.get('score', 0.0):.2f}, "
                  f"серия {entry.get('streak', 0)}, "
                  f"уроков завершено {entry.get('completed_lessons', 0)}")
    an = p.get("analysis") or {}
    if an:
        print(f"=== RepoAnalysis: practice={an.get('has_openspec')} ===")
        print(f"  {an.get('summary')}")
    if p.get("results") is not None:
        print(f"=== Docs results: {len(p['results'])} ===")
        for item in p["results"][:3]:
            print(f"  · {item.get('title')}: {item.get('url')}")


def _matching_reference(pending: str, questions) -> str | None:
    """Эталон висящего вопроса — сверка по префиксу текста."""
    for q in questions:
        if pending[:60] == q.question[:60]:
            return q.reference_answer
    return None


async def _run(args: argparse.Namespace) -> None:
    from sdd_trainer.lessons import load_quiz

    questions = load_quiz("openspec-basics").questions
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"[клиент] сервер поднят: python -m sdd_trainer.mcp (stdio, ADR-010), "
                  f"ученик {args.student} (thread student:{args.student}, ADR-008)")
            last: dict = {}

            if args.list_tools:
                tools = await session.list_tools()
                print("[клиент] инструменты: " + ", ".join(sorted(t.name for t in tools.tools)))

            if args.start:
                print(f'\n[клиент] start_session(student="{args.student}")')
                last = _payload(await session.call_tool(
                    "start_session", {"student": args.student}))
                _show(last)

            if args.calibration is not None:
                print(f"\n[ученик] {args.calibration}")
                last = _payload(await session.call_tool(
                    "answer_calibration",
                    {"student": args.student, "answer": args.calibration}))
                _show(last)

            for _ in range(args.quiz):
                pending = last.get("question") or ""
                answer = _matching_reference(pending, questions)
                if answer is None:
                    answer = questions[0].reference_answer  # blind — увидим guard
                print(f"\n[ученик] {answer}")
                last = _payload(await session.call_tool(
                    "answer_quiz_question",
                    {"student": args.student, "answer": answer}))
                _show(last)

            if args.analyze:
                print(f'\n[клиент] analyze_repo(path="{args.analyze}")')
                _show(_payload(await session.call_tool(
                    "analyze_repo", {"path": args.analyze})))

            if args.search:
                print(f'\n[клиент] search_docs(query="{args.search}")')
                _show(_payload(await session.call_tool(
                    "search_docs", {"query": args.search})))

            if args.progress:
                print(f'\n[клиент] get_progress(student="{args.student}")')
                _show(_payload(await session.call_tool(
                    "get_progress", {"student": args.student})))


def main() -> None:
    parser = argparse.ArgumentParser(prog="mcp_probe")
    parser.add_argument("--student", required=True)
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--calibration")
    parser.add_argument("--quiz", type=int, default=0)
    parser.add_argument("--analyze")
    parser.add_argument("--search")
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args()
    anyio.run(_run, args)


if __name__ == "__main__":
    main()
```

## Honest notes

- **`clarification` path (criterion 5).** Deterministic below the 0.5
  confidence threshold (up to 2 rounds), covered by unit tests
  (`test_low_confidence_routes_to_clarification_without_llm_call`,
  `test_clarification_round_reassesses_and_routes` in
  `tests/unit/test_graph.py`). The Phase 1 live smoke tried twice to elicit
  confidence < 0.5 — the live model stayed confident both times; criterion 5
  needs ≥ 3 paths, met live by `partial` / `knows_it` / `new_topic`.
- **The teach node's fresh-docs decision is model-driven.** Run A's model
  decided `Материалы: скелета достаточно` (no internal search); Run B's
  decided `Материалы: нужен свежий поиск` and the internal
  `search_sdd_docs` fired live (5 Tavily results through the proxy). The code
  is not bent to force a demo — criterion 3b is always provable live via the
  direct `search_docs` tool call.
- **The demo client cannot resume a mid-quiz session.** After a mid-quiz
  restart, `scripts/mcp_demo.py` with the same student calls
  `answer_calibration` against a pending quiz question; the server's
  state-machine guard correctly rejects it (`Сеанс ждёт quiz-вопроса —
  используй answer_quiz_question`) and the demo aborts. The **server** handles
  mid-quiz resume correctly (Run B proves it); the limitation is the demo
  client's fixed script. Use the probe snippet for the restart frame.
- **`route.reason` may carry a parser tail.** In one live run (2026-11-03,
  Run B) the route reason ended with model-output artifacts (`”} трайза
  RouteDecision по схеме.<|function_call|>{`) — an intermittent structured-
  output parsing quirk of the live model, cosmetic only: the route itself,
  the session flow and the verdicts were correct. Not fixed in this docs
  ticket; recorded for the parent issue.
- **Quiz verdicts are deterministic** (weighted token F1 vs the authorial
  references, no LLM judge — ADR-009), so the reference-answer passes
  reproduce exactly (1.00) take after take. A real student answering in
  their own words gets an honest score.

## Live pass log — 2026-11-03

Actual run evidence (fresh runtime artifacts per Step 0; every run exited 0).
Quotes are verbatim client-transcript lines. Full transcripts:
`/tmp/sdd-mcp-smoke/*.log` (ephemeral, not committed).

- **Run A (`mcp-smoke1`, demo, weaker answer):** `Вердикт: level=partial
  confidence=0.7`; `Маршрут: partial — Ученик имеет частичные знания темы:
  знаком с базовыми понятиями, но не разобрался в структуре change proposal
  и не применял знания на практике. Требуется разбор пробелов до квиза.` →
  `=== Урок ===` (skeleton unfolded for level partial) → quiz q1–q5 →
  `Счёт: 1.00 (порог 0.60) / Итог: зачтён` → `Прогресс (training-state):
  openspec-basics: счёт 1.00, серия 1, уроков завершено 1`. The teach node
  logged `Материалы: скелета достаточно` — no internal docs search this run
  (honest note above).
- **Run B (`mcp-smoke2`, probe):** part 1 drove the session to mid-quiz —
  verdict `partial`, lesson, q1+q2 answered, client exit on pending q3; the
  internal tool fired live inside the session: `Инструмент
  search_sdd_docs("openspec change proposal anatomy and workflow for
  console-trainer"): 5 результат(ов)` (criterion 3c). Part 2, a brand-new
  client + server: `<<< type=question · resumed=True · kind=quiz` with the
  pending q3 → three reference answers → `Квиз зачтён: 1.00` → `Прогресс:
  счёт 1.00, серия 2, уроков завершено 2` (criterion 4).
- **Run C (`mcp-smoke3`, demo, default expert answer):** `Маршрут: knows_it —
  Ученик уверенно понимает тему, демонстрирует точное знание модели OpenSpec
  и корректную терминологию. Следует сразу перейти к квизу без лекции.` →
  quiz q1 directly, **no lesson** → 1.00 (criterion 5).
- **Run D (`mcp-smoke4`, demo, "совершенно не знаком"):** `Маршрут:
  new_topic — Ученик явно указал на полное отсутствие знакомства с темой,
  поэтому требуется полный урок с нуля.` → full lesson → quiz → 1.00
  (criterion 5: three paths live with Run A/B).
- **Direct tools (`mcp-smoke5`, probe):** `list_tools` → `Инструменты:
  analyze_repo, answer_calibration, answer_clarification, answer_quiz_question,
  get_progress, search_docs, start_session` (7 tools, criterion 6);
  `analyze_repo("/home/kap/projects/sdd-trainer")` → `RepoAnalysis:
  practice=True`, summary `openspec/ активен: активные changes —
  add-console-trainer, add-mcp-integration, add-project-skeleton; требований
  SHALL — 16; сценариев WHEN/THEN — 14` (criterion 3a);
  `search_docs("OpenSpec spec driven development change proposal workflow")`
  → `Docs results: 5` — live Tavily through the mihomo split tunnel
  (criterion 3b).
- **Guard (`mcp-smoke6`, probe):** `answer_quiz_question` with no session →
  `<<< type=error / message: Нет незавершённого сеанса — сначала вызови
  start_session.` — the state machine guards hold over MCP.
- **Snippet validation (`mcp-smoke7`):** the exact probe snippet above was
  re-run end-to-end after the mid-quiz kill: part 1 exit on pending q3,
  part 2 `resumed=True` → text-matched references q3–q5 → `Вердикт квиза:
  счёт 1.00, зачтён` → progress. Both parts exited 0.

Verdict: **all six criteria visible in the live MCP client transcripts.**
Criterion 4 was demonstrated the hard way over MCP: a server process killed
mid-quiz (client exit), a brand-new server + client resuming from the SQLite
checkpoint, and the quiz completing with the verdict and progress recorded.
