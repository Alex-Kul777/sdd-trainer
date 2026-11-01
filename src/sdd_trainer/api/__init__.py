"""FastAPI transport (phase 2, course criterion 6).

REST endpoints on top of the same graph (ADR-008, AIA_07 course pattern):

- ``POST /lesson`` — synchronous lesson;
- ``POST /lesson/stream`` — ndjson streaming;
- ``POST /quiz/resume`` — resume an interrupted quiz (interrupt + Command +
  thread_id);
- ``GET /progress`` — student progress;
- ``GET /health`` — health check.

Implemented by the ``add-fastapi-service`` change.
"""
