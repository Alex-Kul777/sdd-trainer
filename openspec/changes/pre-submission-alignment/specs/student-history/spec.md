## ADDED Requirements

### Requirement: Student History Pull
The trainer SHALL pull the student's OpenSpec dialogue history via the `openclaw sessions` CLI subprocess and return it as structured records (ADR-007). The CLI output is parsed defensively.

#### Scenario: History available
- **WHEN** get_student_history is called on a machine with the openclaw CLI
- **THEN** the tool returns parsed session records without raising

#### Scenario: CLI missing or failing
- **WHEN** the openclaw CLI is not available or returns an error
- **THEN** the tool returns an empty result with an explanatory note instead of raising
