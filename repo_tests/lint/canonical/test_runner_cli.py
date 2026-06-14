# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""End-to-end CLI tests for the Python runner."""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "tools" / "lint" / "canonical_check.py"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_runner_no_files_no_all_errors():
    result = _run()
    assert result.returncode == 2  # argparse error
    assert "--files" in result.stderr or "--all" in result.stderr


def test_runner_with_clean_file_exits_zero(tmp_path: Path):
    f = tmp_path / "clean.py"
    f.write_text("x = 1\n", encoding="utf-8")
    result = _run("--files", str(f))
    assert result.returncode == 0


def test_runner_explain_known_rule():
    result = _run("--explain", "py-print-smoke")
    assert result.returncode == 0
    assert "py-print-smoke" in result.stdout or "print" in result.stdout.lower()


def test_runner_explain_unknown_rule_exits_2():
    result = _run("--explain", "no-such-rule")
    assert result.returncode == 2


def test_runner_format_json_emits_array():
    result = _run("--files", str(REPO_ROOT / "tools" / "lint" / "canonical_check.py"), "--format", "json")
    assert result.stdout.startswith("[")
