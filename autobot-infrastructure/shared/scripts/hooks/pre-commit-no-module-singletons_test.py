# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-no-module-singletons (#6630).

GH#14167: this is the only Python hook in the directory, which is why
#14151's `set -uo pipefail` grep — a bash-only predicate — structurally
could not find it. Its staged-file helper called `subprocess.run(...)`
with no `check=True` and no returncode inspection: a `git` failure (a
corrupted index, a missing `.git`, a permissions problem) produced empty
stdout, indistinguishable from "nothing staged", so the hook scanned
nothing and reported clean. Fixed by inspecting the returncode and
failing closed, mirroring the bash-hook fix in #14151/#14160.

GH#14162: also tracked at git mode 100644 despite this repo's
`.pre-commit-config.yaml` registering it as `language: python` with a
bare (no-interpreter-prefix) entry — proven empirically (a fresh clone
in a scratch repo) to need the OS executable bit the same way
`language: script` hooks do; `language: python` is not a free pass.
`core.fileMode=false` here hides the mismatch on any existing local
clone.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-module-singletons"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _stage_singleton(repo: Path) -> None:
    f = repo / "autobot_shared" / "mod.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("_tracker = TrackerClass()\n", encoding="utf-8")
    _git(repo, "add", "autobot_shared/mod.py")


def _run_hook(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK_PATH), "--strict", *args],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_blocks_new_singleton_in_strict_mode(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage_singleton(repo)
    result = _run_hook(repo)
    assert result.returncode != 0, result.stdout + result.stderr


def test_allows_clean_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    f = repo / "autobot_shared" / "ok.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "autobot_shared/ok.py")
    result = _run_hook(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_hook_script_exists_and_is_executable() -> None:
    """core.fileMode=false in this repo means `chmod +x` never reaches the
    index (#14051 topic, same gotcha) — a hook committed as 100644 dies
    when a fresh CI checkout sets working-tree perms from git's tracked
    mode. This guards the artifact, not the logic (#14162)."""
    assert os.access(HOOK_PATH, os.X_OK), f"{HOOK_PATH} is not executable on disk"


class TestFailsClosedOnGitFailure:
    """GH#14167: a corrupted `.git/index` used to be indistinguishable from
    "nothing staged" — reproduced with a genuinely staged singleton.
    """

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _stage_singleton(repo)
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = _run_hook(repo)
        assert result.returncode != 0, "a git failure was indistinguishable from 'no violation'"
