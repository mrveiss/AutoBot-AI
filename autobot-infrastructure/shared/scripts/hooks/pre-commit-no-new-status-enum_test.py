# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-no-new-status-enum (#6973, GH#14151 fail-closed
guard).

Issue #14151: see pre-commit-no-new-health-route_test.py's module docstring
for the shared background — same diff-direct shape, same `set -e`-only fix,
same pre-existing `set -u` protection for the missing-lib case, so only the
git-failure path is the genuine, newly-fixed defect here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-new-status-enum"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _stage_status_enum(repo: Path) -> None:
    (repo / "mod.py").write_text("class FooStatus(Enum):\n    A = 1\n", encoding="utf-8")
    _git(repo, "add", "mod.py")


def test_blocks_new_status_enum(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage_status_enum(repo)
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr


def test_allows_exempt_path(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    f = repo / "autobot_shared" / "status_enums.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("class FooStatus(Enum):\n    A = 1\n", encoding="utf-8")
    _git(repo, "add", "autobot_shared/status_enums.py")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


class TestFailsClosedOnGitFailure:
    """GH#14151: a corrupted `.git/index` used to be indistinguishable from
    "no new status-enum declarations" — reproduced with a genuinely staged
    violation.
    """

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _stage_status_enum(repo)
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
        assert result.returncode != 0, "a git failure was indistinguishable from 'no violation'"
