# SDD Trainer

![Tests](https://github.com/Alex-Kul777/sdd-trainer/actions/workflows/tests.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Coverage](https://img.shields.io/badge/coverage-78.35%25-brightgreen)

**SDD Trainer** is a personal AI tutor that teaches **Spec-Driven Development (SDD)** and **OpenSpec** — built with GigaChat (OpenAI-compatible cloud.ru API) and LangGraph.

## Evolution

| Phase | Form | Highlights |
|-------|------|-----------|
| 1 | Console trainer | Lesson -> quiz -> socratic dialogue, memory of progress |
| 2 | FastAPI service | REST + SSE streaming, HITL quizzes over HTTP (done, PSA-T2) |
| 3 | FastAPI + MCP | MCP mounted in the same process at `/mcp` (Streamable HTTP); stdio fallback (done, PSA-T2) |

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
- Domain glossary: [GLOSSARY.md](GLOSSARY.md)
- Defense presentation (slides + live dashboards): [docs/presentation/](docs/presentation/)
