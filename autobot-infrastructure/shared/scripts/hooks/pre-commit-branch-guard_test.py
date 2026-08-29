# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-branch-guard (#1670, GH#14151 fail-closed guard).

Issue #14151: unlike most hooks in this campaign, this one never calls
get_staged_files() or touches `git diff --cached` at all — it only calls
`git rev-parse --git-dir` and `git branch --show-current`, neither of which
reads `.git/index`. The corrupted-index probe every other hook in this
family uses cannot reach either call, so the genuine reproduction is a fake
`git` on PATH that fails only `branch --show-current`, the same technique
pre-commit-worktree-branch-guard_test.py uses for `worktree list`.

This hook does `source lib/_common.sh` unconditionally and now aborts with
a FATAL message on failure (GH#14151's fix), so a missing-dependency
reproduction is included alongside the git-failure one.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-branch-guard"


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


def _init_repo(tmp_path: Path, branch: str = "feature") -> Path:
    _git(tmp_path, "init", "--quiet", "-b", branch)
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("seed\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed")
    return tmp_path


def _write_record(repo: Path, branch: str) -> None:
    (repo / ".git" / ".autobot-pre-commit-branch").write_text(branch, encoding="utf-8")


def test_matching_branch_allows_commit(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, branch="feature")
    _write_record(repo, "feature")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode == 0, result.stdout + result.stderr


def test_mismatched_branch_blocks_commit(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, branch="feature")
    _write_record(repo, "main")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode != 0, result.stdout + result.stderr
    assert "COMMIT ABORTED" in result.stdout


def test_missing_record_file_allows_commit(tmp_path: Path) -> None:
    """No record file means pre-commit-record-branch didn't run — skip
    silently rather than block (e.g. first install)."""
    repo = _init_repo(tmp_path, branch="feature")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode == 0, result.stdout + result.stderr


class TestFailsClosedWhenDependencyMissing:
    """GH#14151: `source lib/_common.sh` now aborts with a FATAL message
    instead of the pre-fix `set -uo pipefail` running past a source failure
    into whatever came next."""

    def test_a_missing_common_lib_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, branch="feature")
        _write_record(repo, "main")  # a genuine mismatch present

        isolated = tmp_path.parent / "isolated-branch-guard"
        isolated.mkdir()
        hook_copy = isolated / HOOK_PATH.name
        hook_copy.write_bytes(HOOK_PATH.read_bytes())
        hook_copy.chmod(0o755)

        result = subprocess.run([str(hook_copy)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
        assert result.returncode != 0, "the hook reported clean with no dependency and a real mismatch present"


class TestFailsClosedWhenGitCannotAnswer:
    """GH#14151: a `git branch --show-current` failure must not be
    indistinguishable from "no mismatch" — reproduced with a fake `git` on
    PATH that fails ONLY `branch --show-current` and delegates everything
    else to the real binary, since a corrupted `.git/index` never reaches
    either git call this hook makes."""

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
        repo = _init_repo(tmp_path, branch="feature")
        _write_record(repo, "main")  # a genuine mismatch present

        fake_bin = self._make_fake_git(tmp_path)
        env = dict(_test_git_env())
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

        result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=env)
        assert result.returncode != 0, "a `git branch --show-current` failure was indistinguishable from 'no mismatch'"
