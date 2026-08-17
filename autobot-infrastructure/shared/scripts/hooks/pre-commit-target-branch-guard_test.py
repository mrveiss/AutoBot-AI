# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-target-branch-guard (#4113, GH#14151 fail-closed
guard).

Issue #14151: like pre-commit-branch-guard, this hook never calls
get_staged_files() or `git diff --cached` — it only calls `git branch
--show-current`, which does not read `.git/index`. The corrupted-index
probe every other hook in this family uses cannot reach it, so the genuine
reproduction is a fake `git` on PATH that fails only `branch --show-current`,
the same technique pre-commit-worktree-branch-guard_test.py uses for
`worktree list`.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-target-branch-guard"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(tmp_path: Path, branch: str) -> Path:
    _git(tmp_path, "init", "--quiet", "-b", branch)
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("seed\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed")
    return tmp_path


def test_allowed_branch_permits_commit(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, branch="issue-9999")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_main_branch_blocks_commit(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, branch="main")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "COMMIT BLOCKED" in result.stdout


class TestFailsClosedWhenDependencyMissing:
    """GH#14151: `source lib/_common.sh` now aborts with a FATAL message
    instead of running past a source failure with `${BOLD}`/`${RED}`/etc.
    unset."""

    def test_a_missing_common_lib_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, branch="main")  # a genuine violation present

        isolated = tmp_path.parent / "isolated-target-branch-guard"
        isolated.mkdir()
        hook_copy = isolated / HOOK_PATH.name
        hook_copy.write_bytes(HOOK_PATH.read_bytes())
        hook_copy.chmod(0o755)

        result = subprocess.run([str(hook_copy)], cwd=repo, capture_output=True, text=True)
        assert result.returncode != 0, "the hook reported clean with no dependency while on a protected branch"


class TestFailsClosedWhenGitCannotAnswer:
    """GH#14151: a `git branch --show-current` failure must not be
    indistinguishable from "not on a protected branch"."""

    def _make_fake_git(self, tmp_path: Path) -> Path:
        real_git_path = None
        for candidate in ("/usr/bin/git", "/bin/git", "/usr/local/bin/git"):
            if Path(candidate).exists():
                real_git_path = candidate
                break
        assert real_git_path, "could not locate a real git binary to delegate to"

        fake_bin = tmp_path.parent / "fake-bin"
        fake_bin.mkdir(exist_ok=True)
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/bin/bash\n"
            f'REAL_GIT="{real_git_path}"\n'
            'if [ "$1" = "branch" ] && [ "$2" = "--show-current" ]; then\n'
            '    echo "fatal: simulated branch failure" >&2\n'
            "    exit 128\n"
            "fi\n"
            'exec "$REAL_GIT" "$@"\n',
            encoding="utf-8",
        )
        fake_git.chmod(fake_git.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return fake_bin

    def test_a_git_branch_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, branch="main")  # a genuine violation present

        fake_bin = self._make_fake_git(tmp_path)
        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

        result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=env)
        assert (
            result.returncode != 0
        ), "a `git branch --show-current` failure was indistinguishable from 'not protected'"
