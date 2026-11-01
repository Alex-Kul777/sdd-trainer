## ADDED Requirements

### Requirement: Source Package Layout
The project SHALL use a src-layout with an importable `sdd_trainer` package that contains the core trainer modules (`config`, `models`, `core/`, `lessons/`, `console/`, `api/`, `mcp/`).

#### Scenario: Skeleton modules import cleanly
- **WHEN** the package is installed with `pip install -e .` and a skeleton module is imported
- **THEN** the import succeeds without errors and without any network calls

### Requirement: GigaChat Configuration via OpenAI-Compatible API
The configuration SHALL access GigaChat through the OpenAI-compatible cloud.ru endpoint `https://foundation-models.api.cloud.ru/v1` using the `GIGACHAT_KEY` environment variable, with `GigaChat/GigaChat-3-Pro` as the primary model and `GigaChat/GigaChat-3.5-Reasoning` as the fallback model.

#### Scenario: Default configuration values
- **WHEN** `GigaChatConfig` is instantiated without arguments
- **THEN** `base_url` is `https://foundation-models.api.cloud.ru/v1`, `model` is `GigaChat/GigaChat-3-Pro`, and `fallback_model` is `GigaChat/GigaChat-3.5-Reasoning`

#### Scenario: Missing API key detected
- **WHEN** `GigaChatConfig` is instantiated with an empty `GIGACHAT_KEY`
- **THEN** `is_configured()` returns `False`

### Requirement: Secret Hygiene
The repository SHALL NOT contain real API keys: secrets SHALL be supplied via a git-ignored `.env` file, while `.env.example` documents the variable names with empty values.

#### Scenario: No secrets in version control
- **WHEN** the repository contents are inspected
- **THEN** `.env` is ignored by git and `.env.example` contains no secret values
