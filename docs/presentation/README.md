# Presentation materials

Defense deck and live dashboards for the project defense (deadline: 2026-11-13).

## Contents

- `deck/presentation.html` — 11-slide defense deck + 2 appendix slides (A1: course-notebooks → project map, A2: three direct inheritances). Self-contained HTML
  (no CDN), 1280×720 slides; open in a browser and navigate with arrow
  keys or the bottom bar. Slide 5 shows the full system architecture
  (C4 container level) with course criteria mapped onto components.
- `deck/presentation.pdf` — the same deck as a 13-page PDF (11 main + 2 appendix).
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
