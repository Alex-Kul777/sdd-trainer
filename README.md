# SDD Trainer

![Tests](https://github.com/Alex-Kul777/sdd-trainer/actions/workflows/tests.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Coverage](https://img.shields.io/badge/coverage-40%25%2B-yellowgreen)

**SDD Trainer** is a personal AI tutor that teaches **Spec-Driven Development (SDD)** and **OpenSpec** — built with GigaChat (OpenAI-compatible cloud.ru API) and LangGraph.

## Evolution

| Phase | Form | Highlights |
|-------|------|-----------|
| 1 | Console trainer | Lesson -> quiz -> socratic dialogue, memory of progress |
| 2 | FastAPI service | Streaming (ndjson), HITL quizzes over HTTP |
| 3 | FastAPI + MCP | Trainer tools exposed to OpenClaw via `/mcp` |

## Quickstart

```bash
pip install -r requirements.txt
pip install -e .
cp .env.example .env   # fill in GIGACHAT_KEY
python app.py
```

## Testing

```bash
make test        # or: pytest -v
```

## Documentation

- Full documentation (Russian): [README_RU.md](README_RU.md)
- Architecture decisions: [DECISIONS.md](DECISIONS.md)
- Domain glossary: [CONTEXT.md](CONTEXT.md)
