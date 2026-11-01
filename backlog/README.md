# Backlog Workflow Guide

Backlog (`backlog/BKL-*.md`) is a lightweight issue-tracking convention adopted
from the rag_GigaChat sample repo (ADR-002).

## Entry structure

Each file `backlog/BKL-NNN-<slug>.md` contains YAML frontmatter + a Markdown
body (see `template.md`):

```yaml
---
id: BKL-001
title: "Short description (max 80 chars)"
priority: high        # high | medium | low
severity: major       # critical | major | minor
status: open          # open | in-progress | blocked | done | rejected
created: 2026-11-01
updated: 2026-11-01
affected_files:
  - src/sdd_trainer/core/graph.py
tags: [graph, routing]
safety_checks:
  - pytest tests/unit/
rollback: "git reset --hard HEAD"
estimated_effort: 30min   # 15min | 30min | 1h | 2h+
---
```

## Priority & severity matrix

| Value | Priority (blocks work?) | Severity (incorrectness?) |
|-------|--------------------------|----------------------------|
| high | Critical path broken; data loss; security | App crash |
| medium | UX degradation; perf regression >20% | Function broken |
| low | Cosmetics; minor warnings | Inconvenient but OK |

Pick order: `priority DESC, severity DESC, created ASC`.

## Workflow states

```
open -> in-progress -> done
              |
           blocked -> (human review / rework)
```

- **open** — ready to pick
- **in-progress** — claimed, feature branch created
- **blocked** — tests failed or a decision is needed
- **done** — safety checks green, commit created
- **rejected** — won't fix / obsolete

## Safety checks

Before: clean worktree (`git status --porcelain`), entry `status: open`,
`safety_checks` non-empty.

After: all `safety_checks` pass, no regressions in `pytest tests/unit/ -q`,
commit message references the entry: `fix: <title> (refs BKL-NNN)`.
