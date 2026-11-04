"""Unit tests for get_student_history — the OpenClaw CLI pull tool (ADR-007, T3).

No real CLI calls: ``subprocess.run`` is monkeypatched at the module seam
(the same boundary-faking pattern as FakeHttpx in test_tools — an external
collaborator replaced, never an internal one mocked). The canned payload is
a worked example of the real ``openclaw sessions --json`` output shape
(inspected 04.11, CLI 2026.9.8), written here independently of the
implementation.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from sdd_trainer.core import tools as tools_module
from sdd_trainer.core.tools import get_student_history

pytestmark = pytest.mark.unit

#: The exact CLI invocation the tool must pin (ADR-007: pin the version,
#: parse carefully — the command itself stays explicit and deterministic).
PINNED_COMMAND = ["openclaw", "sessions", "--json", "--limit", "100"]

#: A canned ``openclaw sessions --json`` response (worked example; extra
#: fields the tool must not depend on are included on purpose).
SESSIONS_PAYLOAD = {
    "path": "/home/kap/.openclaw/agents/nastroyka/agent/openclaw-agent.sqlite",
    "count": 2,
    "totalCount": 69,
    "limitApplied": 100,
    "hasMore": False,
    "activeMinutes": None,
    "sessions": [
        {
            "key": "agent:nastroyka:main:11111111-2222-3333-4444-555555555555",
            "updatedAt": 1793821008288,
            "sessionId": "aaaaaaaa-0000-0000-0000-000000000001",
            "label": "OpenSpec lesson 1: propose",
            "status": "idle",
            "kind": "chat",
            "agentId": "nastroyka",
            "model": "zai-org/GLM-5.2",
            "spawnDepth": 0,
            "contextTokens": 200000,
        },
        {
            "key": "agent:nastroyka:main:99999999-8888-7777-6666-555555555555",
            "updatedAt": 1793810000000,
            "sessionId": "aaaaaaaa-0000-0000-0000-000000000002",
            "label": "SDD quiz: SHALL scenarios",
            "status": "running",
            "kind": "chat",
            "agentId": "nastroyka",
            "model": "zai-org/GLM-5.2",
            "spawnDepth": 0,
            "contextTokens": 200000,
        },
    ],
}

#: What the tool must return for SESSIONS_PAYLOAD: the normalized record
#: fields only (label / status / model — what the lesson prompt consumes).
EXPECTED_SESSIONS = [
    {
        "key": "agent:nastroyka:main:11111111-2222-3333-4444-555555555555",
        "label": "OpenSpec lesson 1: propose",
        "status": "idle",
        "updatedAt": 1793821008288,
        "kind": "chat",
        "agentId": "nastroyka",
        "model": "zai-org/GLM-5.2",
    },
    {
        "key": "agent:nastroyka:main:99999999-8888-7777-6666-555555555555",
        "label": "SDD quiz: SHALL scenarios",
        "status": "running",
        "updatedAt": 1793810000000,
        "kind": "chat",
        "agentId": "nastroyka",
        "model": "zai-org/GLM-5.2",
    },
]


def _install_run(monkeypatch, fake_run) -> list:
    """Patch subprocess.run at the tools module seam; record nothing.

    Returns the list the fake can append recorded calls to (args/kwargs).
    """
    recorded: list = []

    def wrapper(*args, **kwargs):
        recorded.append({"args": args, "kwargs": kwargs})
        return fake_run(*args, **kwargs)

    monkeypatch.setattr(tools_module.subprocess, "run", wrapper)
    return recorded


def _ok_run(payload) -> "subprocess.CompletedProcess":
    return subprocess.CompletedProcess(
        args=PINNED_COMMAND,
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )


class TestGetStudentHistorySuccess:
    """CLI present, valid JSON — parsed records, no exception."""

    def test_parses_valid_json_into_records(self, monkeypatch) -> None:
        _install_run(monkeypatch, lambda *a, **k: _ok_run(SESSIONS_PAYLOAD))

        result = get_student_history()

        assert result["sessions"] == EXPECTED_SESSIONS
        assert result["note"] == ""

    def test_pins_openclaw_sessions_json_command(self, monkeypatch) -> None:
        recorded = _install_run(
            monkeypatch, lambda *a, **k: _ok_run(SESSIONS_PAYLOAD)
        )

        get_student_history()

        (call,) = recorded
        assert list(call["args"][0]) == PINNED_COMMAND
        # The subprocess must not hang forever or leak output to the
        # trainer's stdout (ADR-007: the tool owns the process).
        assert call["kwargs"].get("capture_output") is True
        assert call["kwargs"].get("text") is True
        assert call["kwargs"].get("timeout") is not None

    def test_query_filters_records_by_label_or_key(self, monkeypatch) -> None:
        _install_run(monkeypatch, lambda *a, **k: _ok_run(SESSIONS_PAYLOAD))

        result = get_student_history("quiz")

        assert [record["label"] for record in result["sessions"]] == [
            "SDD quiz: SHALL scenarios"
        ]

    def test_skips_non_dict_session_entries(self, monkeypatch) -> None:
        payload = {
            "count": 2,
            "sessions": ["garbage-string", SESSIONS_PAYLOAD["sessions"][0]],
        }
        _install_run(monkeypatch, lambda *a, **k: _ok_run(payload))

        result = get_student_history()

        assert result["sessions"] == EXPECTED_SESSIONS[:1]


class TestGetStudentHistoryDegradation:
    """CLI missing / failing / garbage — empty result with a note, never
    an exception (the trainer must not crash because of the environment)."""

    def test_cli_missing_returns_empty_with_note(self, monkeypatch) -> None:
        def raise_not_found(*args, **kwargs):
            raise FileNotFoundError("openclaw: no such file or directory")

        _install_run(monkeypatch, raise_not_found)

        result = get_student_history()

        assert result["sessions"] == []
        assert "openclaw" in result["note"]

    def test_cli_nonzero_exit_returns_empty_with_note(self, monkeypatch) -> None:
        def failing_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args,
                returncode=1,
                stdout="",
                stderr="Error: session store locked",
            )

        _install_run(monkeypatch, failing_run)

        result = get_student_history()

        assert result["sessions"] == []
        assert "openclaw" in result["note"]

    def test_cli_timeout_returns_empty_with_note(self, monkeypatch) -> None:
        def raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=PINNED_COMMAND, timeout=30)

        _install_run(monkeypatch, raise_timeout)

        result = get_student_history()

        assert result["sessions"] == []
        assert "openclaw" in result["note"]

    def test_garbage_stdout_returns_empty_with_note(self, monkeypatch) -> None:
        garbage = subprocess.CompletedProcess(
            args=PINNED_COMMAND,
            returncode=0,
            stdout="not json at all {{{",
            stderr="",
        )
        _install_run(monkeypatch, lambda *a, **k: garbage)

        result = get_student_history()

        assert result["sessions"] == []
        assert result["note"] != ""

    def test_payload_without_sessions_list_returns_empty_with_note(
        self, monkeypatch
    ) -> None:
        # The CLI format changed (ADR-007 risk): JSON, but no "sessions"
        # list — the tool must degrade, not crash.
        _install_run(monkeypatch, lambda *a, **k: _ok_run({"items": []}))

        result = get_student_history()

        assert result["sessions"] == []
        assert result["note"] != ""
