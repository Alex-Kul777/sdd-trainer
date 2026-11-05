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

## Presentations & Videos

All under [docs/presentation/](docs/presentation/):

| Folder | What it is | Formats |
|--------|------------|---------|
| [deck/](docs/presentation/deck/) | Defense slides (deck v6, 23 slides + appendix) | HTML, PDF |
| [product-overview/](docs/presentation/product-overview/) | Video: repository & product overview (16 slides, ~10 min, voiceover RU) | MP4 (HQ), HTML, PDF |
| [defense-screencast/](docs/presentation/defense-screencast/) | Video: project defense screencast (deck v6 + live console session, 24 slides, 9:38, voiceover RU) | MP4 (HQ), HTML, PDF |

The live MCP demo runs inside the defense screencast as an animated terminal
slide (from real session logs); the original step-by-step scenario is kept in
[docs/screencast-mcp.md](docs/screencast-mcp.md) (closed).
