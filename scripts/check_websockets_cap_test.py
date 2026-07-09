# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the websockets<16 cap guard (#11030).

The guard fails fast (exit 1, clear message) when autobot-backend's websockets
pin is bumped past the langgraph-sdk <16 cap, and auto-relaxes (exit 0) when
langgraph is removed. Exercised as a subprocess to mirror the CI invocation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("packaging")

_SCRIPT = Path(__file__).resolve().parent / "check_websockets_cap.py"

_GOOD = "langgraph>=1.2.7,<2.0.0\nwebsockets>=15.0,<16\n"
_BAD = "langgraph>=1.2.7,<2.0.0\nwebsockets>=16.0,<17\n"
_NO_LANGGRAPH = "websockets>=16.0,<17\n"
_MISSING_WS = "langgraph>=1.2.7,<2.0.0\n"


def _run(tmp_path: Path, requirements_body: str) -> subprocess.CompletedProcess:
    backend = tmp_path / "autobot-backend"
    backend.mkdir(parents=True, exist_ok=True)
    (backend / "requirements.txt").write_text(requirements_body, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )


def test_compliant_pin_passes(tmp_path: Path) -> None:
    res = _run(tmp_path, _GOOD)
    assert res.returncode == 0, res.stderr
    assert "correctly excludes" in res.stdout


def test_bump_past_cap_fails_with_clear_message(tmp_path: Path) -> None:
    res = _run(tmp_path, _BAD)
    assert res.returncode == 1
    assert "ResolutionImpossible" in res.stderr
    assert "websockets<16" in res.stderr


def test_auto_relaxes_when_langgraph_removed(tmp_path: Path) -> None:
    res = _run(tmp_path, _NO_LANGGRAPH)
    assert res.returncode == 0, res.stderr
    assert "no longer required" in res.stdout


def test_missing_websockets_pin_with_langgraph_fails(tmp_path: Path) -> None:
    res = _run(tmp_path, _MISSING_WS)
    assert res.returncode == 1
    assert "no explicit 'websockets' pin" in res.stderr


def test_repo_backend_requirements_currently_compliant() -> None:
    """The live autobot-backend/requirements.txt must satisfy the guard."""
    repo_root = _SCRIPT.resolve().parents[1]
    res = subprocess.run([sys.executable, str(_SCRIPT)], cwd=repo_root, capture_output=True, text=True)
    assert res.returncode == 0, f"live requirements violate the websockets cap:\n{res.stderr}"
