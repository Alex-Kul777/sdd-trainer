---
id: BKL-NNN
title: "One-line summary of the issue (max 80 chars)"
priority: medium              # high | medium | low
severity: major               # critical | major | minor
status: open                  # open | in-progress | blocked | done | rejected
created: 2026-11-01
updated: 2026-11-01
affected_files:
  - src/sdd_trainer/core/graph.py
tags: [graph, routing]
safety_checks:
  - pytest tests/unit/
rollback: "git reset --hard HEAD"
estimated_effort: 30min       # 15min | 30min | 1h | 2h+
---

## Проблема

Describe the issue:
- What is the symptom?
- When does it occur?
- Impact on users/quality?

Example log excerpt:
```
ERROR in route node: unknown path 'knows_it' for domain 'requirement-writing'
```

## Гипотеза причины

(Optional) Why do you think this happens?
- Timing issue? Configuration problem? Logic error?

## Предлагаемое исправление

Concrete steps to fix:
1. File: `src/sdd_trainer/core/graph.py`
   - Change: add the missing routing path
   - Reason: routing must cover all three paths (course criterion 5)

## Критерии приёмки

- [ ] Logs don't contain the error above
- [ ] `pytest tests/unit/` — all green
- [ ] (Optional) Manual: run a lesson in the affected domain

## Попытки

<!-- Filled on each fix attempt -->
<!-- Example:
- **Attempt 1** (2026-11-01 14:30): ✅ PASS - Fixed in commit abc123d
-->
