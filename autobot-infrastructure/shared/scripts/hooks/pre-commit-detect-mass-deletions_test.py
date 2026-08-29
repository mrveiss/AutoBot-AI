# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-detect-mass-deletions (#4111, GH#14151 fail-closed
guard).

Issue #14151: see pre-commit-no-direct-redis_test.py's module docstring for
the shared background. This hook doesn't use get_staged_files() at all — it
calls `git diff --cached --diff-filter=D` directly into a bare top-level
assignment, so `set -e` alone (no lib/_common.sh change needed) is enough to
make a git failure abort instead of silently reading as "0 deletions,
allow". Its opening also references an unbound color variable only inside
the >50 violation branch, under `set -u`, which independently closed the
"missing lib/_common.sh" case pre-fix — only the git-failure path is the
genuine, newly-fixed defect here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-detect-mass-deletions"


def _test_git_env() -> dict[str, str]:
    """#15246: env for every git subprocess this suite spawns.

    Scrubbed rather than os.environ: the pre-push hook runs this suite with
    GIT_DIR pointing at the worktree it is pushing (every checkout here is
    one), and an unscrubbed `git init`/`git add`/`git commit` in a
    fixture then operates on THAT repository instead of tmp_path's. See
    autobot_shared/paths_test.py and #15246 for the reproduced incident.
    """
    return {**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


DELETION_THRESHOLD = 50


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=_test_git_env())


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _commit_and_stage_deletion_of(repo: Path, count: int) -> None:
    for i in range(count):
        (repo / f"f{i}.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed many files")
    for i in range(count):
        (repo / f"f{i}.txt").unlink()
    _git(repo, "add", "-A")


def test_allows_deletions_at_or_below_threshold(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_and_stage_deletion_of(repo, DELETION_THRESHOLD)
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode == 0, result.stdout + result.stderr


def test_blocks_mass_deletion_above_threshold(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_and_stage_deletion_of(repo, DELETION_THRESHOLD + 10)
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode != 0, result.stdout + result.stderr


class TestFailsClosedOnGitFailure:
    """GH#14151: a corrupted `.git/index` used to be indistinguishable from
    "0 files deleted" — reproduced with a genuine mass-deletion staged.
    """

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit_and_stage_deletion_of(repo, DELETION_THRESHOLD + 10)
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
        assert result.returncode != 0, "a git failure was indistinguishable from '0 deletions'"
