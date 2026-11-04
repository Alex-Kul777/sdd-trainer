## ADDED Requirements

### Requirement: Curriculum Reflects Reality
LESSON_DOMAINS SHALL list exactly the domains that have authored content; roadmap domains live in `docs/roadmap.md`, not in code constants.

#### Scenario: Working domain is the curriculum
- **WHEN** the trainer builds a lesson
- **THEN** the domain is openspec-basics — the single domain with an authored skeleton (`prompts/lessons/`) and quiz (`data/quizzes/`)
