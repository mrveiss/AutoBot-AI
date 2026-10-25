# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A new-branch push is never refused for the number of open PRs (#19397).

Owner decision, 2026-10-23: there is no cap on how many PRs are open on the
remote -- finished local work must be pushed, never held local-only. This
inverts the retired #17006 suite, which pinned a pre-push refusal of every
new-branch push once open PRs reached ``AUTOBOT_OPEN_PR_CAP`` (default 40).

This drives the REAL hook script via git's own pre-push stdin protocol
(``<local-ref> <local-sha> <remote-ref> <remote-sha>``) with ``gh`` stubbed on
a curated ``PATH`` sandbox, so a developer's own authenticated ``gh`` can never
leak in. The stub reports any open-PR count the test asks for -- and logs
every call -- so the assertions cover both "the push passes" and "nothing
asked how many PRs are open".
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.isolated_git import isolated_git_env, make_repo

HOOK_PATH = repo_root() / "tools" / "git-hooks" / "pre-push"

_BASH = shutil.which("bash")
_GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(
    _BASH is None or _GIT is None,
    reason="bash/git not found on this machine -- did not look, not a pass (docs/developer/MEASUREMENT_DISCIPLINE.md)",
)

# Enough for git plumbing and the hook's own coreutils calls (Phase 6 /
# Phase 0c and #16728's prepush_selection), deliberately WITHOUT a real `gh`.
_SANDBOX_TOOLS = (
    "bash",
    "git",
    "sed",
    "grep",
    "head",
    "tail",
    "cut",
    "tr",
    "xargs",
    "sort",
    "uniq",
    "cat",
    "timeout",
    "sleep",
    "wc",
    "date",
    "printf",
    "mkdir",
    "dirname",
    "basename",
    "env",
    "mktemp",
    "rm",
    "python3",
)

_GH_STUB = """#!/usr/bin/env bash
# One line per invocation, "<subcommand> <verb>" only.
printf '%s %s\\n' "$1" "$2" >> "$STATE/gh_calls"

if [ "$1" = "pr" ] && [ "$2" = "list" ]; then
  if [ "${GH_FAIL:-0}" = "1" ]; then
    echo "gh: could not connect to api.github.com" >&2
    exit 1
  fi
  echo "$OPEN_PR_COUNT"
  exit 0
fi

if [ "$1" = "pr" ] && [ "$2" = "view" ]; then
  # Real gh's message for a branch with no open PR yet -- Phase 7 (#16859).
  echo "no pull requests found for branch \\"$3\\"" >&2
  exit 1
fi

echo "fake gh: unexpected invocation: $*" >&2
exit 2
"""


def _make_sandbox(tmp_path: Path, *, include_gh: bool) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in _SANDBOX_TOOLS:
        real = shutil.which(name)
        if real is not None and not (bin_dir / name).exists():
            os.symlink(real, bin_dir / name)
    if include_gh:
        stub = bin_dir / "gh"
        stub.write_text(_GH_STUB, encoding="utf-8")
        stub.chmod(0o755)
    return bin_dir


def _git(cwd: Path, *args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True, env=env)


def _commit(local: Path, env: dict, name: str) -> str:
    (local / name).write_text(f"{name}\n", encoding="utf-8")
    _git(local, "add", name, env=env)
    _git(local, "-c", "commit.gpgsign=false", "commit", "-q", "-m", name, env=env)
    return _git(local, "rev-parse", "HEAD", env=env).stdout.strip()


def _seed_repo(tmp_path: Path, env: dict, branch: str) -> tuple[Path, str, str]:
    """A real repo with `origin/main` and a two-commit feature branch, so
    Phase 0c's `git merge-base "$local_sha" origin/main` always resolves.
    `pytest.ini` is needed by prepush_selection.py's main()."""
    bare = tmp_path / "origin.git"
    local = tmp_path / "local"
    _git(tmp_path, "init", "--quiet", "--bare", str(bare), env=env)
    make_repo(local, default_branch="main")
    (local / "pytest.ini").write_text("[pytest]\npython_files = test_*.py *_test.py\n", encoding="utf-8")
    # #18808: the selection reads the scan-roots record (a missing one fails the selection on
    # purpose), and the hook runs the hardcoded-values audit on every changed path. A synthetic
    # repo has neither, so it gets an empty record and a detector that finds nothing -- this
    # file tests that no open-PR cap remains, not those checks.
    (local / "repo_tests").mkdir()
    (local / "repo_tests" / "_reach_roots_record.py").write_text("REACH_ROOTS = {}\n", encoding="utf-8")
    detector = local / "pipeline-scripts" / "detect-hardcoded-values.sh"
    detector.parent.mkdir()
    detector.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    detector.chmod(0o755)
    _git(local, "add", "pytest.ini", "repo_tests", "pipeline-scripts", env=env)
    _commit(local, env, "README.md")
    _git(local, "remote", "add", "origin", str(bare), env=env)
    _git(local, "push", "-q", "origin", "main", env=env)
    _git(local, "checkout", "-q", "-b", branch, env=env)
    return local, _commit(local, env, "first.txt"), _commit(local, env, "second.txt")


def _run_hook(
    tmp_path: Path, *, include_gh: bool = True, open_prs: int = 0, gh_fail: bool = False, new_branch: bool = True
) -> tuple[subprocess.CompletedProcess, list[str]]:
    bin_dir = _make_sandbox(tmp_path, include_gh=include_gh)
    state = tmp_path / "state"
    state.mkdir()
    env = isolated_git_env(
        {
            "PATH": str(bin_dir),
            "HOME": str(tmp_path),
            "PYTHONPATH": str(repo_root()),
            "STATE": str(state),
            "OPEN_PR_COUNT": str(open_prs),
            # The retired knob: setting it to 1 must change nothing.
            "AUTOBOT_OPEN_PR_CAP": "1",
            "GH_FAIL": "1" if gh_fail else "0",
        }
    )
    branch = "no-open-pr-cap-test"
    local, sha_first, sha_second = _seed_repo(tmp_path, env, branch)
    local_sha, remote_sha = (sha_second, "0" * 40) if new_branch else (sha_second, sha_first)
    ref = f"refs/heads/{branch}"
    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        cwd=local,
        input=f"{ref} {local_sha} {ref} {remote_sha}\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    calls_file = state / "gh_calls"
    calls = calls_file.read_text(encoding="utf-8").splitlines() if calls_file.exists() else []
    return result, calls


@pytest.mark.parametrize("open_prs", [0, 40, 1000])
def test_new_branch_pushes_at_any_open_pr_count(tmp_path: Path, open_prs: int) -> None:
    result, calls = _run_hook(tmp_path, open_prs=open_prs)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pr list" not in calls, f"the hook must not count open PRs, got gh calls {calls}"
    assert "open-pr cap" not in result.stderr.lower(), result.stderr


def test_new_branch_pushes_when_gh_cannot_list_prs(tmp_path: Path) -> None:
    result, _ = _run_hook(tmp_path, open_prs=1000, gh_fail=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_new_branch_pushes_without_gh_installed(tmp_path: Path) -> None:
    result, calls = _run_hook(tmp_path, include_gh=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == [], "no gh binary exists to have been called"


def test_existing_branch_push_still_passes(tmp_path: Path) -> None:
    result, calls = _run_hook(tmp_path, open_prs=1000, new_branch=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pr list" not in calls, calls
