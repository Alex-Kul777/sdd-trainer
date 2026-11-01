"""LangGraph graph of the trainer (criteria 2 and 5).

Topology — AIA_06 routing-agent template: assess -> route -> teach / quiz /
socratic, with a clarification path and a rephrase loop:

- ``assess`` — evaluate the student's level (passive assessment data included);
- ``route`` — routing node with >= 3 paths: knows_it / partial / new_topic
  (+ clarification) — course criterion 5;
- ``teach`` — unfold a lesson from a ``prompts/`` skeleton;
- ``quiz`` — knowledge check with HITL via ``interrupt`` / ``Command``;
- ``socratic`` — follow-up question instead of a lecture.

One graph serves all transports: console (phase 1), FastAPI (phase 2),
MCP (phase 3). Implemented by the ``add-console-trainer`` change (phase 1).
"""
from __future__ import annotations


def build_graph():
    """Assemble and compile the trainer StateGraph (implemented in phase 1)."""
    pass
