# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-no-new-health-route (#3333, GH#14151 fail-closed
guard).

Issue #14151: see pre-commit-no-direct-redis_test.py's module docstring for
the shared background. This hook doesn't use get_staged_files() — it pipes
`git diff --cached -U0` straight into an awk collector, and the result is
captured with a bare top-level `violations=$(collect_violations)`, so
`set -e` alone (no lib/_common.sh change needed) is enough to make a git
failure abort. Its opening banner already references an unbound color
variable under `set -u`, which independently closed the "missing
lib/_common.sh" case pre-fix — only the git-failure path is the genuine,
newly-fixed defect here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-new-health-route"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _stage_health_route(repo: Path) -> None:
    f = repo / "autobot-backend" / "api" / "foo.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text('@router.get("/health")\nasync def h():\n    return {}\n', encoding="utf-8")
    _git(repo, "add", "autobot-backend/api/foo.py")


def test_blocks_new_health_route(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage_health_route(repo)
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr


def test_allows_ordinary_route(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    f = repo / "autobot-backend" / "api" / "foo.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("def h():\n    return {}\n", encoding="utf-8")
    _git(repo, "add", "autobot-backend/api/foo.py")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


class TestFailsClosedOnGitFailure:
    """GH#14151: a corrupted `.git/index` used to be indistinguishable from
    "no new /health routes" — reproduced with a genuinely staged violation.
    """

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _stage_health_route(repo)
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
        assert result.returncode != 0, "a git failure was indistinguishable from 'no violation'"
