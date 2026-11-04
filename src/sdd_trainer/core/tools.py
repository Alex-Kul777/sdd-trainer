"""External tools of the trainer (criterion 3).

Registered as LangGraph tools (AIA_02/AIA_05 patterns):

- ``search_sdd_docs(query)`` — fresh SDD/OpenSpec documentation via Tavily
  (ADR-006; implemented in T4, issue #5 / task 2.3). The teach node calls
  it when the lesson skeleton alone is not enough (task 3.3);
- ``read_openspec_examples(repo)`` — live spec examples via the GitHub API
  (guaranteed second external API, grilling Q3) — later in phase 1;
- ``get_student_history(query)`` — the student's OpenSpec dialogue history via
  the ``openclaw sessions`` CLI subprocess (ADR-007, pull model; implemented
  in T3, issue #14) — graceful degradation when the CLI is missing;
- ``analyze_student_repo(repo_path)`` — passive assessment of the student's
  repository (specs/changes structure, SHALL and WHEN/THEN usage) — task
  2.2, T6 (issue #7). A local filesystem scan: no network, no LLM — the
  evidence the assess node weighs against the self-report (task 3.1).

The seam for tests is the ``client`` parameter of ``search_sdd_docs``: unit
tests inject a fake httpx client (no network), integration tests use the
real Tavily endpoint and are skipped without ``TAVILY_API_KEY``.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

import httpx

from sdd_trainer.config import TavilyConfig
from sdd_trainer.models import RepoAnalysis


def search_sdd_docs(
    query: str,
    *,
    config: Optional[TavilyConfig] = None,
    client: Optional[httpx.Client] = None,
) -> list[dict]:
    """Search fresh SDD/OpenSpec documentation via Tavily (ADR-006, task 2.3).

    POSTs to the Tavily ``/search`` endpoint with the ``TAVILY_API_KEY``
    bearer key and returns ``max_results`` results as ``[{title, url,
    content}, ...]`` — the shape the teach prompt and the session log
    consume (task 3.3). Transport errors propagate: the caller (the teach
    node) decides how resilient the lesson must be; the tool stays honest.

    Args:
        query: the search query (fresh docs for the lesson being unfolded).
        config: Tavily settings; defaults to a fresh ``TavilyConfig()``
            (reads ``TAVILY_API_KEY`` from the environment / ``.env``).
        client: test seam — unit tests inject a fake ``httpx.Client``
            instead of the real one (no network). An injected client stays
            caller-owned (never closed here); without one a short-lived
            client is created and closed per call.

    Returns:
        A list of ``{"title": ..., "url": ..., "content": ...}`` dicts.

    Raises:
        RuntimeError: ``TAVILY_API_KEY`` is not configured — raised before
            any request is made.
        httpx.HTTPError: the Tavily endpoint failed.
    """
    cfg = config if config is not None else TavilyConfig()
    if not cfg.is_configured():
        raise RuntimeError(
            "TAVILY_API_KEY не задан — search_sdd_docs недоступен "
            "(ADR-006: ключ в .env, см. .env.example)"
        )
    if client is not None:
        return _search_via(client, cfg, query)
    with httpx.Client(timeout=cfg.timeout) as own:
        return _search_via(own, cfg, query)


def _search_via(http: httpx.Client, cfg: TavilyConfig, query: str) -> list[dict]:
    """Run one Tavily search over an existing client and normalize results."""
    response = http.post(
        f"{cfg.base_url}/search",
        json={"query": query, "max_results": cfg.max_results},
        headers={"Authorization": f"Bearer {cfg.api_key}"},
        timeout=cfg.timeout,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
        }
        for item in results
    ]


def read_openspec_examples(repo: str) -> list[dict]:
    """Read live OpenSpec examples via the GitHub API (phase 1)."""
    pass


def get_student_history(query: str = "") -> dict:
    """Pull the student's OpenSpec dialogue history via the OpenClaw CLI (ADR-007).

    Runs ``openclaw sessions --json --limit 100`` as a subprocess (pull
    model: the trainer fetches the data itself; the CLI command is pinned
    explicitly — ADR-007 "pin the version, parse carefully") and normalizes
    each session record to the fields the lesson prompts consume:
    ``key / label / status / updatedAt / kind / agentId / model``.

    Defensive parsing throughout: the CLI output format may change between
    versions, so every field is read with ``.get()`` defaults, non-dict
    session entries are skipped, and a payload without a ``"sessions"``
    list degrades gracefully.

    Graceful degradation (the trainer must not crash because of the
    environment): CLI missing (``FileNotFoundError``), non-zero exit,
    timeout, non-JSON stdout, or an unexpected JSON shape all return
    ``{"sessions": [], "note": <explanation>}`` instead of raising.

    Args:
        query: optional case-insensitive substring filter over the session
            ``label`` and ``key`` (e.g. ``"openspec"``); empty — no filter.

    Returns:
        ``{"sessions": [records...], "note": str}`` — parsed records with
        an empty ``note`` on success; on degradation an empty ``sessions``
        list with an explanatory ``note``.
    """
    command = ["openclaw", "sessions", "--json", "--limit", "100"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        return {
            "sessions": [],
            "note": (
                "openclaw CLI не найден в PATH — история диалогов ученика "
                "недоступна; тренер продолжает работу без неё (ADR-007)"
            ),
        }
    except subprocess.TimeoutExpired:
        return {
            "sessions": [],
            "note": (
                "openclaw sessions не ответил за 30 с — история диалогов "
                "ученика недоступна (ADR-007)"
            ),
        }

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        detail = ": " + stderr[:200] if stderr else ""
        return {
            "sessions": [],
            "note": (
                "openclaw sessions завершился с кодом {}{} — история "
                "диалогов ученика недоступна".format(completed.returncode, detail)
            ),
        }

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "sessions": [],
            "note": (
                "openclaw sessions вернул не-JSON вывод — формат CLI не "
                "распознан, история недоступна (ADR-007: парсить аккуратно)"
            ),
        }

    raw_sessions = payload.get("sessions") if isinstance(payload, dict) else None
    if not isinstance(raw_sessions, list):
        return {
            "sessions": [],
            "note": (
                "JSON openclaw sessions не содержит список 'sessions' — "
                "формат CLI изменился? История недоступна (ADR-007)"
            ),
        }

    sessions = [
        {
            "key": str(entry.get("key", "")),
            "label": str(entry.get("label", "")),
            "status": str(entry.get("status", "")),
            "updatedAt": entry.get("updatedAt"),
            "kind": str(entry.get("kind", "")),
            "agentId": str(entry.get("agentId", "")),
            "model": str(entry.get("model", "")),
        }
        for entry in raw_sessions
        if isinstance(entry, dict)
    ]

    if query:
        needle = query.lower()
        sessions = [
            record
            for record in sessions
            if needle in record["label"].lower() or needle in record["key"].lower()
        ]

    return {"sessions": sessions, "note": ""}


def analyze_student_repo(repo_path: str) -> RepoAnalysis:
    """Passively assess the student's repository (task 2.2, issue #7).

    A local filesystem scan (no network, no LLM): looks for ``openspec/``
    and collects the evidence of live SDD practice — stable spec domains
    (``openspec/specs/<domain>/spec.md``), active change proposals
    (``openspec/changes/<name>/`` except ``archive/``), and the SHALL
    requirements / ``#### Scenario:`` blocks across every ``spec.md``
    (stable specs + change deltas). The deterministic ``summary`` is the
    prose that reaches the assessment prompt and the session log.

    A repo without ``openspec/`` is valid evidence (``has_openspec=False``),
    not an error: honestly no visible practice. A missing path is a
    configuration error and raises.

    Args:
        repo_path: path to the student's repository (CLI ``--repo-path``
            or config; fixture repos in tmpdir for tests).

    Returns:
        :class:`~sdd_trainer.models.RepoAnalysis` — the structured scan.

    Raises:
        FileNotFoundError: ``repo_path`` does not exist.
    """
    root = Path(repo_path)
    if not root.exists():
        raise FileNotFoundError(
            "Репозиторий ученика не найден: {!r}".format(str(repo_path))
        )

    openspec_dir = root / "openspec"
    if not openspec_dir.is_dir():
        return RepoAnalysis(
            repo_path=str(repo_path),
            has_openspec=False,
            summary=(
                "openspec/ не найден — живой практики SDD "
                "в репозитории не видно"
            ),
        )

    specs_dir = openspec_dir / "specs"
    spec_domains = (
        sorted(spec.parent.name for spec in specs_dir.glob("*/spec.md"))
        if specs_dir.is_dir()
        else []
    )
    changes_dir = openspec_dir / "changes"
    change_names = (
        sorted(
            entry.name
            for entry in changes_dir.iterdir()
            if entry.is_dir() and entry.name != "archive"
        )
        if changes_dir.is_dir()
        else []
    )

    shall_count = 0
    scenario_count = 0
    for spec_file in openspec_dir.rglob("spec.md"):
        text = spec_file.read_text(encoding="utf-8", errors="replace")
        shall_count += text.count("SHALL")
        scenario_count += text.count("#### Scenario:")

    if not spec_domains and not change_names:
        summary = "openspec/ найден, но спецификаций и изменений в нём нет"
    else:
        parts: list[str] = []
        if spec_domains:
            parts.append("спецификации — " + ", ".join(spec_domains))
        if change_names:
            parts.append("активные changes — " + ", ".join(change_names))
        parts.append("требований SHALL — {}".format(shall_count))
        parts.append("сценариев WHEN/THEN — {}".format(scenario_count))
        summary = "openspec/ активен: " + "; ".join(parts)

    return RepoAnalysis(
        repo_path=str(repo_path),
        has_openspec=True,
        spec_domains=spec_domains,
        change_names=change_names,
        shall_count=shall_count,
        scenario_count=scenario_count,
        summary=summary,
    )
