"""External tools of the trainer (criterion 3).

Registered as LangGraph tools (AIA_02/AIA_05 patterns):

- ``search_sdd_docs(query)`` — fresh SDD/OpenSpec documentation via Tavily
  (ADR-006; GigaSearch fallback);
- ``read_openspec_examples(repo)`` — live spec examples via the GitHub API
  (guaranteed second external API, grilling Q3);
- ``get_student_history(query)`` — the student's OpenSpec dialogue history via
  the ``openclaw sessions`` CLI subprocess (ADR-007, pull model);
- ``analyze_student_repo(repo_path)`` — passive assessment of the student's
  repository (specs/changes quality, SHALL and WHEN/THEN usage).

Phase 0: stubs only — no network calls. ``search_sdd_docs`` and
``read_openspec_examples`` land in phase 1 (``add-console-trainer``);
the OpenClaw-facing tools in phase 3 (``add-mcp-integration``).
"""
from __future__ import annotations


def search_sdd_docs(query: str) -> list[dict]:
    """Search fresh SDD/OpenSpec documentation via Tavily (phase 1)."""
    pass


def read_openspec_examples(repo: str) -> list[dict]:
    """Read live OpenSpec examples via the GitHub API (phase 1)."""
    pass


def get_student_history(query: str = "") -> list[dict]:
    """Extract the student's OpenSpec history via the OpenClaw CLI (phase 3)."""
    pass


def analyze_student_repo(repo_path: str) -> dict:
    """Passively assess the student's repository (phase 3)."""
    pass
