# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every env file detect-environment.sh can select must actually exist (#15143).

Four of five branches used to name a file nothing tracks or generates
(``.env.wsl-docker-desktop``, ``.env.linux-native`` twice, ``.env.distributed``)
-- silently exporting nothing rather than a real config. Asserted statically
against the real tracked inventory, rather than driving ``detect_environment()``
through every OS/Docker branch, which would mean faking ``/proc/version`` and a
Docker socket for each case just to reach the part under test: the mapping.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

_SCRIPT_PATH = Path(__file__).resolve().parent / "detect-environment.sh"

# Every case branch's ENV_FILE="..." assignment.
_ENV_FILE_ASSIGNMENT_RE = re.compile(r'ENV_FILE="(\.env\.[A-Za-z0-9._-]+)"')


def _selectable_env_files() -> set[str]:
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    return set(_ENV_FILE_ASSIGNMENT_RE.findall(source))


def _tracked_env_files() -> set[str]:
    """Tracked ``.env*`` files, repo-root-relative regardless of cwd.

    ``:/`` anchors the pathspec to the worktree root and ``--full-name``
    returns paths relative to it, so this does not depend on where the
    script (or this test) happens to live in the tree.
    """
    result = subprocess.run(
        ["git", "-C", str(_SCRIPT_PATH.parent), "ls-files", "--full-name", "--", ":/.env*", ":/docker/.env*"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    )
    return {line.rsplit("/", 1)[-1] for line in result.stdout.splitlines() if line}


def test_the_script_exists() -> None:
    assert _SCRIPT_PATH.is_file(), f"{_SCRIPT_PATH} not found -- did it move?"


def test_the_extraction_found_selectable_files() -> None:
    """An empty extraction would make the assertion below pass vacuously."""
    selectable = _selectable_env_files()
    assert selectable, "no ENV_FILE=\"...\" assignment found in detect-environment.sh -- regex or script drifted"


def test_the_tracked_set_is_not_empty() -> None:
    """AC2: the oracle itself must not be vacuous."""
    assert _tracked_env_files(), "git ls-files found no tracked .env* file -- checked against nothing"


def test_every_selectable_env_file_is_tracked() -> None:
    selectable = _selectable_env_files()
    tracked = _tracked_env_files()
    missing = sorted(selectable - tracked)
    assert not missing, (
        f"detect-environment.sh can select {missing}, which this repo does not "
        f"track. Tracked .env* files: {sorted(tracked)}"
    )


def test_a_missing_file_fails_loudly_rather_than_exporting_nothing() -> None:
    """#15143 AC1's other half: a genuine miss must not be a silent no-op."""
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "exit 1" in source, "the not-found branch no longer fails -- it must not silently continue"
    assert "using defaults" not in source, "the silent-continue message this issue removed is back"
