"""Unit tests for analyze_student_repo — the passive repo scan (task 2.2, issue #7).

No network: the tool is a local filesystem scan, so the tests build fixture
repositories in tmpdir (per the brief) — a rich openspec/ repo, a plain repo
without openspec/, and a missing path. Expected values are literals counted
by hand from the fixture content, independent of the implementation (no
tautological recomputation). The archive/ folder must not count as an
active change (openspec convention, see the repo's own openspec/changes/).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sdd_trainer.core.tools import analyze_student_repo
from sdd_trainer.models import RepoAnalysis

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> None:
    """Create parent dirs and write a fixture file (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_plain_repo(root: Path) -> Path:
    """A student repo without openspec/ — a plain code project."""
    _write(root / "README.md", "# My project\n")
    _write(root / "app.py", "print('hello')\n")
    return root


def make_rich_repo(root: Path) -> Path:
    """A student repo with living openspec/ — specs, an active change, archive.

    Hand-counted expectations (independent truth):
    - spec domains: console-trainer, glossary (2);
    - active changes: add-console-trainer (archive/old-change excluded);
    - SHALL: 2 (console-trainer) + 1 (glossary) + 1 (change delta) = 4;
    - scenarios: 1 + 1 + 1 = 3.
    """
    _write(root / "README.md", "# Student project\n")
    _write(
        root / "openspec/specs/console-trainer/spec.md",
        "# console-trainer\n\n"
        "### Requirement: Session\nThe trainer SHALL run a session.\n\n"
        "#### Scenario: Full session\n"
        "- **WHEN** the student starts\n"
        "- **THEN** the trainer assesses\n\n"
        "### Requirement: Routing\nThe router SHALL pick a path.\n",
    )
    _write(
        root / "openspec/specs/glossary/spec.md",
        "# glossary\n\n"
        "### Requirement: Terms\nThe glossary SHALL define terms.\n\n"
        "#### Scenario: Term lookup\n"
        "- **WHEN** a term is asked\n"
        "- **THEN** the glossary answers\n",
    )
    _write(root / "openspec/changes/add-console-trainer/proposal.md", "# Proposal\n")
    _write(root / "openspec/changes/add-console-trainer/tasks.md", "# Tasks\n")
    _write(
        root
        / "openspec/changes/add-console-trainer/specs/console-trainer/spec.md",
        "### Requirement: Assess\nThe graph SHALL assess passively.\n\n"
        "#### Scenario: Repo evidence\n"
        "- **WHEN** a repo is given\n"
        "- **THEN** the analysis weighs in\n",
    )
    _write(root / "openspec/changes/archive/old-change/proposal.md", "# Old\n")
    return root


class TestAnalyzeStudentRepo:
    """The tool returns structured evidence (RepoAnalysis), honestly."""

    def test_plain_repo_reports_no_openspec(self, tmp_path: Path) -> None:
        repo = make_plain_repo(tmp_path / "plain-repo")

        analysis = analyze_student_repo(str(repo))

        assert isinstance(analysis, RepoAnalysis)
        assert analysis.has_openspec is False
        assert analysis.spec_domains == []
        assert analysis.change_names == []
        assert analysis.shall_count == 0
        assert analysis.scenario_count == 0
        assert analysis.summary == (
            "openspec/ не найден — живой практики SDD в репозитории не видно"
        )

    def test_rich_repo_counts_specs_changes_requirements(self, tmp_path: Path) -> None:
        repo = make_rich_repo(tmp_path / "rich-repo")

        analysis = analyze_student_repo(str(repo))

        assert analysis.has_openspec is True
        assert analysis.spec_domains == ["console-trainer", "glossary"]
        assert analysis.change_names == ["add-console-trainer"]  # archive excluded
        assert analysis.shall_count == 4  # 2 + 1 stable specs + 1 change delta
        assert analysis.scenario_count == 3  # 1 + 1 stable specs + 1 change delta
        assert analysis.summary == (
            "openspec/ активен: спецификации — console-trainer, glossary; "
            "активные changes — add-console-trainer; требований SHALL — 4; "
            "сценариев WHEN/THEN — 3"
        )

    def test_missing_path_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            analyze_student_repo(str(tmp_path / "no-such-repo"))

    def test_empty_openspec_dir_is_honest_no_practice(self, tmp_path: Path) -> None:
        """openspec/ exists but has no specs/changes — honest empty evidence."""
        repo = tmp_path / "empty-openspec"
        _write(repo / "openspec" / ".gitkeep", "")

        analysis = analyze_student_repo(str(repo))

        assert analysis.has_openspec is True
        assert analysis.spec_domains == []
        assert analysis.change_names == []
        assert analysis.shall_count == 0
        assert analysis.scenario_count == 0
        assert analysis.summary == (
            "openspec/ найден, но спецификаций и изменений в нём нет"
        )
