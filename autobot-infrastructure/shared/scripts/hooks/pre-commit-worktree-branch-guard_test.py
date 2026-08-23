# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-worktree-branch-guard (#1654, GH#14151 fail-closed
guard).

Issue #14151 review (round 2): this hook's `git worktree list --porcelain`
call was fed into the loop through PROCESS substitution —
`done < <(git worktree list --porcelain)` — whose exit status never reaches
the calling shell. Neither `set -e` nor `set -u` can observe a process
substitution's failure, so corrupting `.git/index` (the probe used for
every other hook in this campaign) cannot reach this code path at all:
`git worktree list` doesn't read the index. The genuine reproduction needs
a `git` that fails specifically on `worktree list` while every other git
call still succeeds normally — a fake `git` shim on PATH, not a corrupted
repository.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-worktree-branch-guard"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("seed\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed")
    return tmp_path


def _stage_worktree_conflict(repo: Path, linked_wt: Path) -> None:
    """Make `repo` (the main working tree) and a linked worktree both
    resolve to the same branch — the real shape this hook guards against.
    `git worktree add -b` refuses to double-check-out a branch, so the
    conflict is engineered by adding the linked worktree for a NEW branch
    first, then pointing the main tree's HEAD at that same branch directly
    (a plain file write, not `git checkout` — this simulates the race the
    hook exists to catch, not a state a normal `git checkout` could reach
    in one step)."""
    _git(repo, "worktree", "add", "-q", "-b", "shared-branch", str(linked_wt))
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/shared-branch\n", encoding="utf-8")


def test_no_conflict_is_allowed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_conflict_is_blocked(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    linked_wt = tmp_path.parent / "linked-wt"
    _stage_worktree_conflict(repo, linked_wt)
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "shared-branch" in result.stdout


class TestFailsClosedWhenGitWorktreeListFails:
    """GH#14151 review: a corrupted `.git/worktrees` tree or disk pressure
    makes `git worktree list` itself fail — reproduced with a fake `git` on
    PATH that fails ONLY `worktree list` and delegates everything else to
    the real binary, since a corrupted `.git/index` cannot reach this path
    (`git worktree list` never reads the index).
    """

    def _make_fake_git(self, tmp_path: Path) -> Path:
        # GH#14884: this used to resolve git with
        # `subprocess.run(["command", "-v", "git"])`. `command` is a POSIX shell
        # BUILTIN, not a binary, so subprocess raised FileNotFoundError on every
        # machine with no `command` executable on PATH — before the hardcoded
        # candidate list below it ever ran, and its result was never read anyway.
        # That left this fail-closed property unverified. shutil.which answers
        # the same question in-process, and honours PATH instead of guessing.
        real_git_path = shutil.which("git")
        assert real_git_path, "could not locate a real git binary to delegate to"

        fake_bin = tmp_path.parent / "fake-bin"
        fake_bin.mkdir(exist_ok=True)
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/bin/bash\n"
            f'REAL_GIT="{real_git_path}"\n'
            'if [ "$1" = "worktree" ] && [ "$2" = "list" ]; then\n'
            '    echo "fatal: simulated worktree list failure" >&2\n'
            "    exit 128\n"
            "fi\n"
            'exec "$REAL_GIT" "$@"\n',
            encoding="utf-8",
        )
        fake_git.chmod(fake_git.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return fake_bin

    def test_a_git_worktree_list_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        linked_wt = tmp_path.parent / "linked-wt-2"
        _stage_worktree_conflict(repo, linked_wt)

        fake_bin = self._make_fake_git(tmp_path)
        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

        result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=env)

        assert result.returncode != 0, "a `git worktree list` failure was indistinguishable from 'no conflict'"
