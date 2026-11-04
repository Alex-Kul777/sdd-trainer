# API Guide — REST + SSE + MCP in one FastAPI process (ADR-001, PSA-T2)

One FastAPI process serves REST, SSE streaming, and the MCP Streamable HTTP
endpoint mounted at `/mcp`. The stdio MCP server (`python -m sdd_trainer.mcp`,
ADR-010) remains the fallback transport. Start:

```bash
python -m sdd_trainer.app        # or: python app.py  (uvicorn, localhost:8000)
```

## Endpoints

| Method | Path | What it does |
|--------|------|--------------|
| GET | `/health` | Status + trainer version |
| POST | `/sessions/{student}/start` | Create/resume the checkpointed thread; returns the calibration question |
| POST | `/sessions/{student}/answer` | Resume the graph with `Command(resume=answer)`; returns the next interrupt payload (calibration / clarification / quiz question) or the final verdict |
| GET | `/sessions/{student}/stream` | SSE stream of graph events; `?answer=...` resumes an interrupted session mid-stream (HITL, AIA_07 pattern) |
| POST | `/mcp/` | MCP Streamable HTTP (initialize handshake, tools) — the same 7 tools as stdio |

## Examples

```bash
curl -s localhost:8000/health

curl -s -X POST localhost:8000/sessions/alice/start

curl -s -X POST localhost:8000/sessions/alice/answer \
  -H 'Content-Type: application/json' -d '{"answer": "specs are stable, changes are proposals"}'

curl -N "localhost:8000/sessions/alice/stream"          # SSE lesson stream
```

## Guarantees (pinned by tests, `tests/unit/test_http_app.py`)

- REST payloads are byte-identical to the MCP tools' payloads for the same
  student thread — one core, three entrances (console, REST, MCP).
- State lives only in the SqliteSaver checkpoint (`thread_id student:<name>`,
  ADR-008): kill the server mid-quiz, restart, `start` returns `resumed=True`
  with the pending question.
- The mounted MCP endpoint runs a real initialize handshake (verified by the
  test-suite's in-memory transport); DNS-rebinding protection is configured
  for localhost (the trainer is a local service).
