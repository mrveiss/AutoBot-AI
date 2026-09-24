# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for scripts/hooks/session-stop-orphan-check.sh (#17410).

The Stop hook fires from whatever directory the session is in. Outside a work
tree it must exit 0 quietly: a non-zero exit is reported as a hook error on
every session stop (477 in one 14-day window) and the check itself never runs.
"""

from __future__ import annotations

import json
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
    assert all(c.startswith("$CLAUDE_PROJECT_DIR/") for c in orphan), orphan
