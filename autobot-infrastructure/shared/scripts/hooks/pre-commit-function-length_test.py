# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-function-length (#620, GH#14151 fail-closed guard).

Issue #14151: see pre-commit-no-direct-redis_test.py's module docstring for
the shared background. This hook's opening banner already references an
unbound color variable under `set -u` (independently closing the
"missing lib/_common.sh" case pre-fix), so only the git-failure path is the
genuine, newly-fixed defect here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-function-length"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _long_function_source(lines: int = 80) -> str:
    body = "\n".join(f"    x{i} = {i}" for i in range(lines))
    return f"def big():\n{body}\n"


def test_blocks_overlong_function(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "bad.py").write_text(_long_function_source(), encoding="utf-8")
    _git(repo, "add", "bad.py")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr


def test_allows_short_function(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "ok.py").write_text("def small():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", "ok.py")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


class TestFailsClosedOnGitFailure:
    """GH#14151: a corrupted `.git/index` used to be indistinguishable from
    "nothing staged" — reproduced with a genuinely staged violation.
    """

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        (repo / "bad.py").write_text(_long_function_source(), encoding="utf-8")
        _git(repo, "add", "bad.py")
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
        assert result.returncode != 0, "a git failure was indistinguishable from 'no violation'"
