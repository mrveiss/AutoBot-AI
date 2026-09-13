# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""detect-environment.sh only selects env files the repo actually has (#15143).

Four of five branches used to name a file nothing tracks, so the script
always fell through to "using defaults" silently. Forces each branch via
AUTOBOT_ENVIRONMENT (the script prefers an already-set value over detecting
one) and checks the outcome against the real, on-disk tracked set rather than
against a copy of the script's own list -- a wrong list in the script would
make a self-referential check pass regardless.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from repo_tests._reach import declare

from autobot_shared.paths import project_root

SCRIPT = "autobot-infrastructure/shared/scripts/utilities/detect-environment.sh"

#: Branches that select a real, tracked env file.
_RESOLVED = ("wsl-docker-desktop", "no-docker")
#: Branches with no tracked file to map onto -- the script must fail loudly.
_UNRESOLVED = ("linux-native", "wsl-native-docker", "containerized")


def _tracked_env_files(root: Path | None = None) -> list[str]:
    base = root if root is not None else project_root()
    return sorted(p.name for p in base.glob(".env*") if p.is_file())


#: Pinned to the live population (6 `.env*` files as of #15143). A guard whose
#: discovery quietly returned fewer -- a moved/renamed file, a `.glob()` typo --
#: would otherwise still pass `test_the_tracked_set_is_not_empty` as long as the
#: count stayed above zero; the floor catches a shrink the boolean check can't.
REACH = declare(
    "detect-environment-env-files",
    discover=_tracked_env_files,
    floor=6,
    growth=2,
    what=".env* files tracked at the repo root",
)


def _run(env_value: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash unavailable")
    return subprocess.run(
        [bash, "-c", f'AUTOBOT_ENVIRONMENT={env_value} source "{SCRIPT}"; echo "RESULT:$AUTOBOT_ENV_FILE"'],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(project_root()),
    )


def test_the_tracked_set_is_not_empty() -> None:
    assert _tracked_env_files(), "no .env* file is tracked -- nothing for this script to select"


@pytest.mark.parametrize("env_value", _RESOLVED)
def test_resolved_branches_select_a_tracked_file(env_value: str) -> None:
    result = _run(env_value)
    assert result.returncode == 0, result.stdout + result.stderr

    [result_line] = [line for line in result.stdout.splitlines() if line.startswith("RESULT:")]
    selected = result_line.removeprefix("RESULT:")
    assert selected in _tracked_env_files(), f"{env_value!r} selected {selected!r}, which the repo does not track"


@pytest.mark.parametrize("env_value", _UNRESOLVED)
def test_unresolved_branches_fail_loudly(env_value: str) -> None:
    result = _run(env_value)
    assert result.returncode != 0, f"{env_value!r} must fail rather than silently export nothing useful"
    assert "#15143" in result.stdout, "the failure message must name what's missing, not just exit"
