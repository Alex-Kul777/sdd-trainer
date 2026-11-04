# Presentation materials

Defense deck and live dashboards for the project defense (deadline: 2026-11-13).

## Contents

- `deck/presentation.html` — 10-slide defense deck. Self-contained HTML
  (no CDN), 1280×720 slides; open in a browser and navigate with arrow
  keys or the bottom bar.
- `deck/presentation.pdf` — the same deck as a 10-page PDF.
- `deck/speaker_notes.html` — speaker notes: an oral script that
  complements the slides instead of repeating them.
- `index.html` — index of four live dashboards:
  1. `01-chat-trenera.html` — verbatim transcript of a full training
     session: calibration → partial verdict → lesson → quiz → F1 pass.
  2. `02-kod-po-kriteriyam.html` — repository code mapped to the six
     course criteria, with ADR references and line numbers.
  3. `03-zhivoj-log.html` — live logs: the MCP server killed mid-quiz and
     resumed from the checkpoint by a new process (`resumed=True`).
  4. `04-langgraph-faza-2.html` — compiled LangGraph graph dump plus the
     MCP layer of Phase 2.

## Provenance

Every quote on the slides and dashboards is verbatim from the live
verification runs of 2026-11-03 (a full session and a kill/restart
experiment through the MCP stdio server) and from the repository code.
Nothing is a staged or handwritten scenario.
