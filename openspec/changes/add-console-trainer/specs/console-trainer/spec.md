## ADDED Requirements

### Requirement: Console Trainer Session
The trainer SHALL run an end-to-end console session for the `openspec-basics` domain: assess the student's level, route to a lesson path, teach from the lesson skeleton, and score a quiz against reference answers.

#### Scenario: Full session for a new student
- **WHEN** the student starts the console trainer for the `openspec-basics` domain with empty training state
- **THEN** the trainer assesses the level, selects one of at least three route paths, delivers a lesson expanded from the skeleton, and scores the quiz against reference answers

### Requirement: Routing With At Least Three Paths
The routing node SHALL select between `knows_it`, `partial`, and `new_topic` paths, plus `clarification` when the assessment is inconclusive.

#### Scenario: Route selected by assessment
- **WHEN** the assess node produces a level for the domain
- **THEN** the route node selects exactly one path and the selection is visible in the session log

### Requirement: GigaChat Via OpenAI-Compatible API With Structured Output
The trainer SHALL call GigaChat through the OpenAI-compatible cloud.ru endpoint with structured output via tools + tool_choice, and SHALL fall back to the reasoning model when the primary model fails (ADR-005).

#### Scenario: Structured decision parsed
- **WHEN** a node requires a structured decision (assessment, routing, quiz scoring)
- **THEN** the LLM response is parsed into the declared Pydantic schema without free-text parsing

### Requirement: Two External Tools
The trainer SHALL provide at least two tools: `analyze_student_repo` (student repository analysis for passive assessment) and `search_sdd_docs` (web search via Tavily, ADR-006).

#### Scenario: Tool calls visible in the session log
- **WHEN** the session runs passive assessment or the lesson needs fresh documentation
- **THEN** tool calls and their results are visible in the session log

### Requirement: Persistent Progress
The trainer SHALL persist graph state with a SQLite checkpointer under a per-student thread id and SHALL update training-state.json with domain, score, and streak (ADR-008).

#### Scenario: State survives restart
- **WHEN** a console session is interrupted and restarted with the same student thread id
- **THEN** the trainer resumes from the checkpoint and training state reflects the last completed activity
