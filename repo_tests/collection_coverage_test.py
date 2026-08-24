# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every test file must be accounted for by some runner (#13653).

`ci.yml` collects a hand-curated list of directories. Nothing checked that the
list covered the repository, so whole trees fell out of CI silently:

* `scripts/` — seven suites guarding the pre-commit checkers, run by nothing
  until #13660.
* `scripts/lib/*_test.sh` — including the #10035 branch-deletion regression
  suite, never executed by anything until `repo_tests/shell_lib_test.py`.
* `test_mcp_subscriptions.py` at the repository root — a **SyntaxError** that
  had survived since #9275 because no collector ever tried to import it
  (#13662).

The failure mode is not merely lost coverage: an uncollected directory will
happily hold a test file that does not even parse.

This guard makes exclusions *explicit*. Every tracked test file must be either
collected by one of the two pytest invocations, run by a named workflow, or
listed in ``INTENTIONALLY_UNCOLLECTED`` with a reason. Adding a new test
directory that nothing runs fails here instead of going unnoticed.

The allowlist records the status quo as measured; a reason string is not an
endorsement, and several entries are worth revisiting.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def project_root() -> Path:
    """Repository root via git, or a skip when this is not a git checkout.

    Deliberately not `autobot_shared.paths.project_root()` (#13652): that helper
    is not on this branch yet, and this module already shells out to git, so the
    same call answers both questions without a second root derivation. Once the
    #13659 stack lands, switching to the canonical resolver removes this
    dependency entirely.

    The whole module is git-driven — every check enumerates *tracked* files — so
    without git there is nothing to assert rather than something failing. This
    repository ships a `.dockerignore` that strips `.git` from build contexts,
    so a git-less checkout is a real configuration here, not a hypothetical, and
    it must skip rather than raise `CalledProcessError` out of ten tests.
    """
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent),
        check=False,
    )
    if out.returncode != 0:
        pytest.skip("not a git checkout — these checks enumerate tracked files")
    return Path(out.stdout.strip())

#: Directories collected by ci.yml's backend pytest invocation.
BACKEND_RUN = {
    "autobot-backend",
    "autobot_shared",
    "autobot-tts-worker",
    "repo_tests",
    "tools",
    "scripts",
}

#: Collected by the separate slm-backend invocation (#13084 keeps them apart:
#: both backends define identically-named top-level packages).
SLM_RUN = {"autobot-slm-backend"}

#: Path prefix -> why nothing collects it. Reasons, not endorsements.
INTENTIONALLY_UNCOLLECTED = {
    "autobot-npu-worker": (
        "not in either ci.yml invocation; pytest.ini only --ignore's its resources/ "
        "subdirectory (Windows-only, PySide6), so the other suites are simply uncollected"
    ),
    "pipeline-scripts": "run by unwired-tracker-audit.yml, not the main suite",
    "autobot-infrastructure": "conftest imports unified_config_manager, which no longer resolves",
    "plugins": "optional plugin tools; deps not installed by the CI requirements",
    "autobot-frontend": "Python helper beside the Vue app; not part of either backend suite",
}


def _tracked_test_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*_test.py", "test_*.py"],
        capture_output=True,
        text=True,
        cwd=str(project_root()),
        check=False,
    )
    return [line for line in out.stdout.split() if line]


def _classify(path: str) -> str | None:
    """Return the runner accounting for *path*, or None if unaccounted."""
    top = Path(path).parts[0]
    if top in BACKEND_RUN:
        return "backend-run"
    if top in SLM_RUN:
        return "slm-run"
    for prefix, reason in INTENTIONALLY_UNCOLLECTED.items():
        if path.startswith(f"{prefix}/"):
            return f"excluded: {reason}"
    return None


def test_every_test_file_is_accounted_for() -> None:
    """No tracked test file may be invisible to every runner."""
    files = _tracked_test_files()
    assert files, "git ls-files matched no test files — the glob may have drifted"

    unaccounted = sorted(p for p in files if _classify(p) is None)

    assert not unaccounted, (
        "these test files are collected by no pytest invocation and are not on "
        "INTENTIONALLY_UNCOLLECTED — add them to ci.yml's collection list, or to "
        f"the allowlist with a reason:\n  " + "\n  ".join(unaccounted)
    )


def test_no_test_file_sits_at_the_repository_root() -> None:
    """The root is in neither collection list, so a test there runs nowhere.

    This is what hid `test_mcp_subscriptions.py`'s SyntaxError for months
    (#13662). Colocate the file with its subject instead.
    """
    root_level = sorted(p for p in _tracked_test_files() if "/" not in p)

    assert not root_level, (
        "test files at the repository root are collected by nothing — move them "
        f"beside their subject:\n  " + "\n  ".join(root_level)
    )


def test_allowlist_has_no_stale_entries() -> None:
    """An allowlist prefix that matches nothing is dead weight."""
    files = _tracked_test_files()

    stale = sorted(
        prefix
        for prefix in INTENTIONALLY_UNCOLLECTED
        if not any(p.startswith(f"{prefix}/") for p in files)
    )

    assert not stale, (
        "INTENTIONALLY_UNCOLLECTED entries match no test file and should be "
        f"removed: {stale}"
    )


@pytest.mark.parametrize("directory", sorted(BACKEND_RUN | SLM_RUN))
def test_collected_directories_still_exist(directory: str) -> None:
    """A renamed directory would silently stop being collected."""
    assert (project_root() / directory).is_dir(), (
        f"{directory} is named in ci.yml's collection list but does not exist"
    )
