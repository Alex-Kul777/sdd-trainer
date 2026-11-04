## ADDED Requirements

### Requirement: Single FastAPI Process
The trainer SHALL expose REST endpoints and the MCP Streamable HTTP endpoint in one FastAPI process; the MCP app is mounted at `/mcp` via `FastMCP.streamable_http_app()` (ADR-001). The stdio server remains the fallback transport (ADR-010).

#### Scenario: Health check
- **WHEN** a client calls GET /health
- **THEN** the server responds with status ok and the trainer version

### Requirement: Sync Session Endpoints
The REST API SHALL drive the checkpointed graph stepwise, mirroring the MCP session tools: start creates or resumes the student thread and returns the calibration question; answer resumes the graph with `Command(resume=...)` and returns the next interrupt payload or the final verdict (ADR-008, ADR-010).

#### Scenario: Start and answer over REST
- **WHEN** a client POSTs a start request and then an answer for the same student
- **THEN** the responses match the MCP tools' payloads for the same thread

### Requirement: Streaming Mode
The REST API SHALL stream graph events over SSE so long lessons arrive progressively (AIA_07 streaming pattern).

#### Scenario: Lesson streamed
- **WHEN** a client opens the stream endpoint during a lesson
- **THEN** events arrive incrementally and the session state persists in the checkpointer
