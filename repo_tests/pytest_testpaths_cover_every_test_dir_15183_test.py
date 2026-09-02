# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A pytest.ini cannot silently omit a directory that holds tests (#15183).

`autobot-infrastructure/shared/tests/pytest.ini` declared
`testpaths = unit integration e2e`. `e2e` does not exist; `distributed/`,
`performance/` and a root-level test module do, and were named by nothing.

The consequence was a split between two ways of running the same tree. CI passes
that directory as an explicit path argument, and pytest ignores `testpaths`
entirely when paths are given on the command line — so CI collected everything
while a developer running bare `pytest` there collected a subset that included a
directory which is not on disk. A test added to `distributed/` ran in CI and
never locally, and the config gave no hint of it.

This guard is about the *stale list*, not the specific entries: any enumeration
has to be maintained by hand, and the entry naming a deleted directory is what
that looks like when it is not.
"""

from __future__ import annotations

import configparser
from pathlib import Path
from typing import List, Set

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_SKIP_PARTS = {".git", "node_modules", "venv", ".venv", "__pycache__", ".worktrees"}


def _pytest_inis() -> List[Path]:
    # Filtered on the path RELATIVE to the repo root, not the absolute one: a
    # checkout inside `.worktrees/` would otherwise match its own skip entry and
    # this guard would find nothing while reporting success.
    return [
        p
        for p in REPO_ROOT.rglob("pytest.ini")
        if not _SKIP_PARTS & set(p.relative_to(REPO_ROOT).parts)
    ]


def _declared_testpaths(ini: Path) -> List[str]:
    parser = configparser.ConfigParser()
    parser.read(ini, encoding="utf-8")
    for section in ("pytest", "tool:pytest"):
        if parser.has_option(section, "testpaths"):
            return parser.get(section, "testpaths").split()
    return []


def _dirs_holding_tests(root: Path) -> Set[Path]:
    """Directories under *root* that contain at least one `test_*.py`."""
    found: Set[Path] = set()
    for path in root.rglob("test_*.py"):
        if _SKIP_PARTS & set(path.relative_to(root).parts):
            continue
        found.add(path.parent)
    return found


def _covered(root: Path, declared: List[str], directory: Path) -> bool:
    """Is *directory* reachable from one of the declared testpaths?"""
    for entry in declared:
        base = (root / entry).resolve()
        if directory == base or base in directory.parents:
            return True
    return False


#: Configs whose omissions predate this guard, with the issue tracking each.
#: Shrink-only: an entry is removed when its issue closes, and a NEW omission in
#: an exempt config still fails `test_every_declared_testpath_exists` below. The
#: alternative was to widen the root config here, which would have added 67
#: never-executed test functions to the PR gate as a side effect of writing a
#: guard -- a decision that belongs to #15476, not to this file.
KNOWN_UNCOVERED: dict[str, str] = {
    "pytest.ini": (
        "#15476: testpaths omits autobot-npu-worker (8 files, 67 test functions "
        "named by no workflow either) and four autobot-infrastructure/shared/scripts "
        "directories. Whether those join the PR gate or the marker suite is a "
        "decision, not a wiring fix."
    ),
}

_INIS = [ini for ini in _pytest_inis() if _declared_testpaths(ini)]


def test_the_guard_found_a_config_to_check() -> None:
    """Guard the guard: no configs found means every case below is vacuous."""
    assert _INIS, "no pytest.ini with a testpaths setting was found — the sweep broke"


@pytest.mark.parametrize("ini", _INIS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_every_declared_testpath_exists(ini: Path) -> None:
    """A path naming a deleted directory is the stale half of the same defect."""
    root = ini.parent
    missing = [entry for entry in _declared_testpaths(ini) if not (root / entry).exists()]

    assert not missing, (
        f"{ini.relative_to(REPO_ROOT)} declares testpaths that do not exist: {missing}. "
        "A stale entry is silent — pytest does not warn, it just selects less than "
        "the author believes."
    )


@pytest.mark.parametrize("ini", _INIS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_every_directory_holding_tests_is_selected(ini: Path) -> None:
    root = ini.parent
    declared = _declared_testpaths(ini)
    uncovered = sorted(
        str(d.relative_to(root)) for d in _dirs_holding_tests(root) if not _covered(root, declared, d)
    )
    if uncovered and str(ini.relative_to(REPO_ROOT)) in KNOWN_UNCOVERED:
        pytest.skip(KNOWN_UNCOVERED[str(ini.relative_to(REPO_ROOT))])

    assert not uncovered, (
        f"{ini.relative_to(REPO_ROOT)} declares testpaths={declared}, which does not "
        f"reach these directories holding test_*.py: {uncovered}. Those tests run "
        "when the directory is passed explicitly (as CI does) and not when someone "
        "runs bare pytest here — so the two disagree about what the suite is."
    )


def test_every_exemption_names_a_live_config() -> None:
    """The exemption table shrinks; it must not accumulate dead entries.

    An exemption for a config that no longer exists -- or that no longer has an
    omission -- is indistinguishable from one that is still needed, which is how
    a temporary allowance becomes permanent.
    """
    known = set(KNOWN_UNCOVERED)
    live = {str(ini.relative_to(REPO_ROOT)) for ini in _INIS}
    assert known <= live, f"exemptions naming a config that has no testpaths: {sorted(known - live)}"

    for name in sorted(known):
        ini = REPO_ROOT / name
        root = ini.parent
        declared = _declared_testpaths(ini)
        uncovered = [d for d in _dirs_holding_tests(root) if not _covered(root, declared, d)]
        assert uncovered, (
            f"{name} is exempt but now covers every test directory — remove its "
            "KNOWN_UNCOVERED entry in the same commit that fixed it."
        )
