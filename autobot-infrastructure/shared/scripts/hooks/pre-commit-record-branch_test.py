# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-record-branch (#1670, GH#14151 fail-closed guard).

Issue #14151: this hook has no lib/_common.sh dependency at all — it only
calls `git rev-parse --git-dir` and `git branch --show-current` directly,
so `set -uo pipefail` -> `set -euo pipefail` alone is the fix (no guarded
source needed, matching PR #14160's own table: "record-branch (no lib
dependency — -e only)"). Neither call reads `.git/index`, so the
corrupted-index probe every other hook in this family uses cannot reach
either — reproduced instead with a fake `git` on PATH that fails one call
at a time, the same technique pre-commit-worktree-branch-guard_test.py uses
for `worktree list`.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-record-branch"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(tmp_path: Path, branch: str = "feature") -> Path:
    _git(tmp_path, "init", "--quiet", "-b", branch)
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("seed\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed")
    return tmp_path


def test_records_current_branch(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, branch="feature")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    record = repo / ".git" / ".autobot-pre-commit-branch"
    assert record.read_text(encoding="utf-8").strip() == "feature"


class TestFailsClosedWhenGitCannotAnswer:
    """GH#14151: neither `git rev-parse --git-dir` nor `git branch
    --show-current` failing may be indistinguishable from "recorded (or
    intentionally skipped) cleanly" — each is reproduced with a fake `git`
    on PATH that fails ONLY that one subcommand and delegates the rest to
    the real binary."""

    def _make_fake_git(self, tmp_path: Path, name: str, fail_args: tuple[str, ...]) -> Path:
        real_git_path = None
        for candidate in ("/usr/bin/git", "/bin/git", "/usr/local/bin/git"):
            if Path(candidate).exists():
                real_git_path = candidate
                break
        assert real_git_path, "could not locate a real git binary to delegate to"

        condition = " && ".join(f'[ "${i + 1}" = "{arg}" ]' for i, arg in enumerate(fail_args))
        fake_bin = tmp_path.parent / f"fake-bin-{name}"
        fake_bin.mkdir(exist_ok=True)
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/bin/bash\n"
            f'REAL_GIT="{real_git_path}"\n'
            f"if {condition}; then\n"
            '    echo "fatal: simulated failure" >&2\n'
            "    exit 128\n"
            "fi\n"
            'exec "$REAL_GIT" "$@"\n',
            encoding="utf-8",
        )
        fake_git.chmod(fake_git.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return fake_bin

    def _run_with_fake_git(self, repo: Path, fake_bin: Path) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        return subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=env)

    def test_a_git_dir_lookup_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, branch="feature")
        fake_bin = self._make_fake_git(tmp_path, "gitdir", ("rev-parse", "--git-dir"))
        result = self._run_with_fake_git(repo, fake_bin)
        assert result.returncode != 0, "a `git rev-parse --git-dir` failure was silently swallowed"

    def test_a_git_branch_lookup_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, branch="feature")
        fake_bin = self._make_fake_git(tmp_path, "branch", ("branch", "--show-current"))
        result = self._run_with_fake_git(repo, fake_bin)
        assert result.returncode != 0, "a `git branch --show-current` failure was silently swallowed"
