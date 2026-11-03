# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A reach floor nobody pinned is computed from the base commit, and still fires (#19676).

The property a floor exists for is that a narrowed sweep fails. A floor computed from the live
tree would follow the narrowing down, so these tests narrow ``discover`` on the PR side only and
require the failure. Declarations are built with ``Reach(...)`` rather than ``declare()`` so the
synthetic ones never join the registry the meta-tests sweep.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from repo_tests import _reach_base
from repo_tests._ratchet_base import BaseUnavailable
from repo_tests._reach import Reach, ReachFloorError

from autobot_shared.paths import scrubbed_git_env

_GLOB = "repo_tests/*_test.py"


def _tests_under(root: Path) -> list[Path]:
    return sorted(root.glob(_GLOB))


def _computed(name: str, discover, *, growth: int = 0, skips: int = 0) -> Reach[Path]:
    return Reach(name=name, discover=discover, pinned_floor=0, what="test files", growth=growth, skips=skips)


def test_an_unpinned_floor_is_the_base_population_less_its_allowance() -> None:
    reach = _computed("base-floor::bottom-of-window", _tests_under, growth=20, skips=3)
    at_base = len(_tests_under(_reach_base.base_tree()))
    assert at_base > 100, "the base tree was checked out with its test files"
    assert (reach.computed, reach.floor) == (True, at_base - 3 - 20)
    assert reach.staleness(_reach_base.REPO_ROOT) is None, "a computed floor has no constant to go stale"


def test_a_discover_narrowed_on_the_pr_side_fails() -> None:
    """The base sees every test file; the PR side's sweep silently drops most of them."""
    base = _reach_base.base_tree().resolve()

    def narrowed(root: Path) -> list[Path]:
        found = _tests_under(root)
        return found if root.resolve() == base else found[:10]

    reach = _computed("base-floor::narrowed", narrowed, growth=20)
    with pytest.raises(ReachFloorError, match="floor is"):
        reach.examined(_reach_base.REPO_ROOT)
    with pytest.raises(ReachFloorError):
        reach.completed(10)


def test_the_unnarrowed_sweep_passes_against_the_same_floor() -> None:
    reach = _computed("base-floor::honest", _tests_under, growth=20)
    assert len(reach.examined(_reach_base.REPO_ROOT)) >= reach.floor


def test_an_empty_tree_still_fails_the_computed_floor(tmp_path: Path) -> None:
    with pytest.raises(ReachFloorError):
        _computed("base-floor::empty", _tests_under, growth=20).examined(tmp_path)


def test_an_unreadable_base_refuses_instead_of_passing(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_base(_root: Path) -> str:
        raise BaseUnavailable("no base in this test")

    monkeypatch.setattr(_reach_base, "_TREE", {})
    monkeypatch.setattr(_reach_base, "_BASE_COUNT", {})
    monkeypatch.setattr(_reach_base, "base_commit", no_base)
    with pytest.raises(BaseUnavailable):
        _ = _computed("base-floor::no-base", _tests_under).floor


def test_a_pinned_floor_is_read_as_declared_and_never_touches_the_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_reach_base, "base_tree", lambda: pytest.fail("a pinned floor read the base"))
    reach = Reach(name="base-floor::pinned", discover=_tests_under, pinned_floor=7, what="test files")
    assert (reach.computed, reach.floor) == (False, 7)


def test_the_base_tree_is_outside_the_repo_and_removed_with_its_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_reach_base, "_TREE", {})
    tree = _reach_base.base_tree()
    assert _reach_base.REPO_ROOT not in tree.resolve().parents
    _reach_base.remove_base_tree(tree)
    listed = subprocess.run(
        ["git", "-C", str(_reach_base.REPO_ROOT), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout
    assert not tree.exists() and str(tree) not in listed
