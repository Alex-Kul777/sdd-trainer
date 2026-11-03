## ADDED Requirements

### Requirement: MCP Server Over The Trainer Graph
The trainer SHALL expose its session flow over MCP (Model Context Protocol) via a stdio server built on the official Python SDK (FastMCP), without rewriting the core graph (ADR-010).

#### Scenario: MCP client starts a session
- **WHEN** an MCP client calls the session-start tool for a student
- **THEN** the server resumes or creates the checkpointed graph thread and returns the calibration question

### Requirement: Stepwise Session Tools
The session tools SHALL drive the checkpointed graph stepwise: each tool call advances the graph to the next interrupt and returns its payload; state persists in the SQLite checkpointer under the student thread id (ADR-008).

#### Scenario: Quiz answered stepwise over MCP
- **WHEN** the client sends an answer to a quiz question
- **THEN** the server returns either the next question or the F1 verdict, and progress survives reconnection

### Requirement: Direct Tool Access
The MCP server SHALL expose `analyze_student_repo` and `search_sdd_docs` as MCP tools so any MCP client can use the trainer's tools directly.

#### Scenario: Repo analysis over MCP
- **WHEN** a client calls the repo analysis tool with a repository path
- **THEN** the server returns the structured RepoAnalysis

### Requirement: Progress Query
The MCP server SHALL expose a progress tool returning the student's training state: domain, score, streak, and completed lessons.

#### Scenario: Progress after a session
- **WHEN** a client queries progress after a completed quiz
- **THEN** the server returns the updated training state

### Requirement: MCP Demo Client
The repository SHALL include an MCP client script that runs a full trainer session against the server over stdio, usable as the screencast demo of the prototype.

#### Scenario: Automated demo run
- **WHEN** the demo client runs against the MCP server with a live GigaChat key
- **THEN** it completes a full session (calibration, assessment, lesson, quiz, summary) and prints the visible session flow
