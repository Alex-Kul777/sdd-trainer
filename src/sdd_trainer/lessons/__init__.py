"""Lesson content for the 6 SDD domains — the trainer's curriculum.

Domains (PLAN-FINAL-PROJECT.md, section 2):

1. ``sdd-fundamentals`` — spec as the source of truth, plan before code;
2. ``openspec-structure`` — specs/ vs changes/;
3. ``requirement-writing`` — SHALL requirements + WHEN/THEN scenarios;
4. ``change-proposals`` — proposal -> design -> tasks;
5. ``openspec-workflow`` — explore -> propose -> apply -> archive;
6. ``brownfield-sdd`` — incremental changes in a live project.

Lesson skeletons (few-shot prompts) live in ``prompts/``; quizzes with
reference answers live in ``data/`` (hybrid authorship, grilling Q10).
Content lands in phase 1 (``add-console-trainer`` change).
"""
from __future__ import annotations

LESSON_DOMAINS: list[str] = [
    "sdd-fundamentals",
    "openspec-structure",
    "requirement-writing",
    "change-proposals",
    "openspec-workflow",
    "brownfield-sdd",
]
