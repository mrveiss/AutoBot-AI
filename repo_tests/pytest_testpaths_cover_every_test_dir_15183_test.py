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


#: Both halves of pytest.ini's `python_files`. Sweeping only `test_*.py` was
#: #15018's defect one guard over: `*_test.py` is the majority form in this
#: tree, so eight directories holding nothing but that half were invisible to
#: this check -- among them autobot-infrastructure/shared/scripts/monitoring,
#: .../setup/knowledge and shared/tools, which no testpath reaches (#15178).
#: `test_every_pattern_pytest_collects_by_is_swept` pins this list to the ini.
_TEST_FILE_GLOBS = ("test_*.py", "*_test.py")


def _dirs_holding_tests(root: Path) -> Set[Path]:
    """Directories under *root* holding at least one file pytest would collect."""
    found: Set[Path] = set()
    for pattern in _TEST_FILE_GLOBS:
        for path in root.rglob(pattern):
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
        "#15476: testpaths does not reach 16 directories holding files pytest "
        "would collect. Re-measured under #15178, because every number in the "
        "reason this replaced was wrong. autobot-npu-worker is omitted whole: 14 "
        "tracked test files across 7 directories, of which 11 -- holding 168 test "
        "functions -- sit outside the resources/ subtree pytest.ini --ignore's at "
        "line 181, not the '8 files, 67 test functions' recorded here before. "
        "autobot-infrastructure contributes SEVEN directories, not four: "
        "shared/scripts and its analysis/, logging/, monitoring/, "
        "setup/knowledge/ and utilities/ subdirectories, plus shared/tools -- the "
        "last three were missed because this module swept only `test_*.py` and "
        "they hold `*_test.py`. The remaining two are autobot-frontend/tests and "
        "plugins/core-plugins/video-generation-plugin/tools, both named by "
        "marker-tests.yml or by nothing rather than by this ini. "
        "Why the exemption cannot simply be dropped: widening testpaths adds "
        "never-executed tests to the PR gate as a side effect of writing a guard "
        "-- ~30 ad-hoc scripts under shared/scripts/analysis/, and npu modules "
        "importing `openvino`, which requirements-ci.txt does not carry. That is "
        "#15476's decision, not this file's. It is NOT the INTERNALERROR that "
        "reason used to name: #14917 put shared/scripts/test_alertmanager.py's "
        "`sys.exit` behind a `main()` guard, so the import is inert and that "
        "blocker is spent -- pytest.ini lines 106-110 now record it as spent too."
    ),
}

_INIS = [ini for ini in _pytest_inis() if _declared_testpaths(ini)]


def test_every_pattern_pytest_collects_by_is_swept() -> None:
    """`_TEST_FILE_GLOBS` must be exactly pytest.ini's `python_files`.

    A half pytest collects by that this sweep does not glob is a directory this
    guard cannot see -- a silent omission inside the guard against silent
    omissions (#15018, #15178).
    """
    parser = configparser.ConfigParser()
    parser.read(REPO_ROOT / "pytest.ini", encoding="utf-8")
    declared = parser.get("pytest", "python_files").split()

    assert declared, "pytest.ini declares no `python_files`, so this sweep has nothing to mirror"
    assert set(declared) == set(_TEST_FILE_GLOBS), (
        "pytest.ini's `python_files` and this module's sweep patterns disagree, so a "
        "directory holding only the unswept half is invisible here: "
        f"pytest.ini={sorted(declared)} sweep={sorted(_TEST_FILE_GLOBS)}"
    )


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
