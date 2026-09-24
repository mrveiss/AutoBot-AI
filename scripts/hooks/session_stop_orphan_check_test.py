# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for scripts/hooks/session-stop-orphan-check.sh (#17410).

The Stop hook fires from whatever directory the session is in. Outside a work
tree it must exit 0 quietly: a non-zero exit is reported as a hook error on
every session stop (477 in one 14-day window) and the check itself never runs.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

SCRIPT = Path(__file__).resolve().parent / "session-stop-orphan-check.sh"
SETTINGS = Path(__file__).resolve().parents[2] / ".claude" / "settings.json"


def _run(cwd: Path, ceiling: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(cwd), "GIT_CEILING_DIRECTORIES": str(ceiling)},
    )


def test_outside_a_work_tree_exits_zero(tmp_path: Path) -> None:
    """`cd "$(git_repo_root)" || exit 0` never fired: `cd ""` succeeds, and a
    later git call then died under set -e with 128."""
    res = _run(tmp_path, tmp_path.parent)
    assert res.returncode == 0, res.stdout + res.stderr


def test_inside_a_git_dir_exits_zero(tmp_path: Path) -> None:
    """The second field shape: cwd inside `.git`, which is a repo but no work tree."""
    subprocess.run(["git", "init", "-q", str(tmp_path / "r")], check=True, env=scrubbed_git_env())
    res = _run(tmp_path / "r" / ".git", tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr


def test_stop_hook_does_not_resolve_its_path_from_the_cwd() -> None:
    """`$(git rev-parse --show-toplevel)/scripts/...` collapsed to `/scripts/...`
    outside a work tree, so the hook exited 127 before the script could run."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    commands = [h["command"] for group in settings["hooks"]["Stop"] for h in group["hooks"]]
    orphan = [c for c in commands if "session-stop-orphan-check.sh" in c]
    assert orphan, "Stop hook no longer runs the orphan check"
    assert all(c.startswith('"$CLAUDE_PROJECT_DIR"/') for c in orphan), orphan


def _hook_commands() -> list[str]:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    return [h["command"] for groups in settings["hooks"].values() for g in groups for h in g["hooks"]]


def test_no_hook_command_word_splits_the_project_dir() -> None:
    """Hook commands run through `sh -c`, so an unquoted $CLAUDE_PROJECT_DIR
    splits on a space in the checkout path and the hook exits 127 -- the same
    symptom as the cwd route above. Class-wide, so a new hook copying an
    unquoted neighbour fails here."""
    unquoted = [c for c in _hook_commands() if re.search(r'(?<!")\$\{?CLAUDE_PROJECT_DIR', c)]
    assert not unquoted, unquoted


def test_stop_hook_runs_from_a_project_dir_with_a_space(tmp_path: Path) -> None:
    """Behavioural twin of the class check: resolve the real command through
    `sh -c` with a project dir whose path contains a space."""
    spaced = tmp_path / "with space"
    spaced.symlink_to(SETTINGS.parents[1], target_is_directory=True)
    (cmd,) = [c for c in _hook_commands() if "session-stop-orphan-check.sh" in c]
    res = subprocess.run(
        ["sh", "-c", cmd],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "CLAUDE_PROJECT_DIR": str(spaced),
            "GIT_CEILING_DIRECTORIES": str(tmp_path.parent),
        },
    )
    assert res.returncode == 0, res.stdout + res.stderr
