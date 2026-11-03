# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A reach floor nobody pinned is computed from the BASE's declaration, and still fires (#19676).

The property a floor exists for is that a narrowed sweep fails. The base is measured by the
guard module as it was at the base commit, in its own process, so a narrowing in the PR's
``discover`` cannot move the floor. The narrowing test below is a real edit: a different
``discover`` under the name of an existing guard, whose base declaration is left as it was.
Synthetic declarations are built with ``Reach(...)`` so they never join the registry the
meta-tests sweep.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from repo_tests import _reach, _reach_base
from repo_tests._ratchet_base import BaseUnavailable
from repo_tests._reach import Reach, ReachFloorError
from repo_tests.audio_extension_allowlist_test import REACH as REAL

from autobot_shared.paths import scrubbed_git_env


@pytest.fixture(autouse=True)
def _own_population_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """``population()`` is memoised per (name, root); these declarations share a name on purpose."""
    monkeypatch.setattr(_reach, "_MEASURED", {})


def _as_real(discover, *, pinned_floor: int = 0) -> Reach[Path]:
    """A declaration under the real guard's name and module, with this test's ``discover``."""
    return Reach(
        name=REAL.name,
        discover=discover,
        pinned_floor=pinned_floor,
        what=REAL.what,
        growth=REAL.growth,
        skips=REAL.skips,
        module=REAL.module,
    )


def test_the_base_is_measured_by_the_bases_own_declaration() -> None:
    at_base = _reach_base.base_population(_as_real(lambda _root: []))
    assert at_base > 1000, "the base's declaration measured its own population, not this test's empty discover"
    assert _as_real(lambda _root: []).floor == at_base - REAL.skips - REAL.growth


def test_a_discover_narrowed_in_the_pr_fails_against_the_unedited_base() -> None:
    """The PR's discover keeps one file in ten; the floor still comes from the base's full sweep."""
    narrowed = _as_real(lambda root: list(REAL.discover(root))[::10])
    with pytest.raises(ReachFloorError, match="floor is"):
        narrowed.examined(_reach_base.REPO_ROOT)
    with pytest.raises(ReachFloorError):
        narrowed.completed(len(narrowed.population(_reach_base.REPO_ROOT)))


def test_the_unnarrowed_sweep_passes_against_the_same_floor() -> None:
    honest = _as_real(REAL.discover)
    assert len(honest.examined(_reach_base.REPO_ROOT)) >= honest.floor


def test_an_empty_tree_still_fails_the_computed_floor(tmp_path: Path) -> None:
    with pytest.raises(ReachFloorError):
        _as_real(REAL.discover).examined(tmp_path)


def test_a_declaration_the_base_does_not_have_is_refused_not_passed() -> None:
    new = Reach(name="base-floor::new-in-this-pr", discover=REAL.discover, pinned_floor=0, what="x", module=__name__)
    with pytest.raises(BaseUnavailable, match="pins floor= until it lands"):
        _ = new.floor


def test_a_floor_that_would_be_zero_or_less_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(_reach_base._BASE_COUNT, "base-floor::tiny", 5)
    tiny = Reach(name="base-floor::tiny", discover=REAL.discover, pinned_floor=0, what="x", growth=10)
    with pytest.raises(BaseUnavailable, match="asserts nothing"):
        _ = tiny.floor


def test_an_unreadable_base_refuses_instead_of_passing(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_base(_root: Path) -> str:
        raise BaseUnavailable("no base in this test")

    monkeypatch.setattr(_reach_base, "_TREE", {})
    monkeypatch.setattr(_reach_base, "_BASE_COUNT", {})
    monkeypatch.setattr(_reach_base, "_BASE_FAILED", {})
    monkeypatch.setattr(_reach_base, "base_commit", no_base)
    with pytest.raises(BaseUnavailable):
        _ = _as_real(REAL.discover).floor


def test_a_pinned_floor_is_read_as_declared_and_never_touches_the_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_reach_base, "base_tree", lambda: pytest.fail("a pinned floor read the base"))
    reach = _as_real(REAL.discover, pinned_floor=7)
    assert (reach.computed, reach.floor) == (False, 7)


def test_pinned_by_design_names_only_pinned_declarations() -> None:
    from repo_tests.reach_declarations_test import _declarations  # noqa: PLC0415 - imports every guard

    by_name = {reach.name: reach for reach in _declarations()}
    for name, reason in _reach_base.PINNED_BY_DESIGN.items():
        assert reason.strip(), f"{name}: an exemption needs its reason"
        assert name in by_name and by_name[name].pinned_floor > 0, f"{name} is listed but not pinned"


def test_the_base_tree_is_outside_the_repo_and_removed_with_its_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_reach_base, "_TREE", {})
    tree = _reach_base.base_tree()
    assert _reach_base.REPO_ROOT not in tree.resolve().parents
    assert tree.name.startswith(_reach_base.TREE_PREFIX), "each process gets its own temp directory"
    _reach_base.remove_base_tree(tree)
    listed = subprocess.run(
        ["git", "-C", str(_reach_base.REPO_ROOT), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout
    assert not tree.exists() and str(tree) not in listed
