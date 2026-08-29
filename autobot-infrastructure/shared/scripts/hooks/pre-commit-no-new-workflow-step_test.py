# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-no-new-workflow-step (#6951, GH#14151 fail-closed
guard).

Issue #14151: see pre-commit-no-new-health-route_test.py's module docstring
for the shared background — same diff-direct shape, same `set -e`-only fix,
same pre-existing `set -u` protection for the missing-lib case, so only the
git-failure path is the genuine, newly-fixed defect here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-new-workflow-step"


def _test_git_env() -> dict[str, str]:
    """#15246: env for every git subprocess this suite spawns.

    Scrubbed rather than os.environ: the pre-push hook runs this suite with
    GIT_DIR pointing at the worktree it is pushing (every checkout here is
    one), and an unscrubbed `git init`/`git add`/`git commit` in a
    fixture then operates on THAT repository instead of tmp_path's. See
    autobot_shared/paths_test.py and #15246 for the reproduced incident.
    """
    return {**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=_test_git_env())


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _stage_workflow_step(repo: Path) -> None:
    (repo / "mod.py").write_text("class WorkflowStep:\n    pass\n", encoding="utf-8")
    _git(repo, "add", "mod.py")


def test_blocks_new_workflow_step(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage_workflow_step(repo)
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode != 0, result.stdout + result.stderr


def test_allows_subclass(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "mod.py").write_text("class WorkflowStep(WorkflowTask):\n    pass\n", encoding="utf-8")
    _git(repo, "add", "mod.py")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode == 0, result.stdout + result.stderr


class TestFailsClosedOnGitFailure:
    """GH#14151: a corrupted `.git/index` used to be indistinguishable from
    "no new workflow-shape declarations" — reproduced with a genuinely
    staged violation.
    """

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _stage_workflow_step(repo)
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
        assert result.returncode != 0, "a git failure was indistinguishable from 'no violation'"
