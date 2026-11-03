# Tasks: Add Console Trainer (Phase 1)

## 1. LLM client
- [x] 1.1 Verify exact model IDs via models.list (primary + fallback)
- [x] 1.2 Implement llm_manager: OpenAI-compatible client, structured output via tools + tool_choice (ADR-005)
- [x] 1.3 Fallback to the reasoning model on primary model failure

## 2. Schemas & tools
- [x] 2.1 Pydantic schemas: Assessment, RouteDecision, QuizResult (course pattern AIA_02)
- [x] 2.2 Tool analyze_student_repo: scan the student repository for openspec/ usage
- [x] 2.3 Tool search_sdd_docs: Tavily client (ADR-006)

## 3. Graph
- [x] 3.1 assess node: passive assessment via analyze_student_repo + calibration question
- [x] 3.2 route node: knows_it / partial / new_topic (+ clarification)
- [x] 3.3 teach node: expand the lesson skeleton per level; search_sdd_docs on demand
- [x] 3.4 quiz node: questions from the JSON quiz, F1 vs reference answers

## 4. Persistence
- [x] 4.1 SqliteSaver checkpointer, per-student thread_id (ADR-008)
- [x] 4.2 training-state.json updates: domain, score, streak

## 5. Content
- [x] 5.1 Lesson skeleton openspec-basics.md (sections per ADR-009)
- [x] 5.2 Quiz openspec-basics.json: questions, reference answers, weights

## 6. Console
- [x] 6.1 REPL in __main__: input/print glue over the graph, session summary at exit

## 7. Tests & smoke
- [x] 7.1 Unit tests at the graph seam with FakeLLM (routing, checkpoint, training-state, F1)
- [x] 7.2 Integration tests with real GigaChat (skip without GIGACHAT_KEY)
- [x] 7.3 Manual smoke checklist: criteria 1–5 visible in session logs
