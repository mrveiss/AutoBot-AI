# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A reach floor costs one base walk per module asked about, never one per registered declaration (#17810).

A computed floor is measured at the base commit by walking the base tree with each declaration's own
``discover``. That walk used to cover EVERY registered declaration (~200, about 74s) the first time any
floor was read, and ``reach_declarations_test`` registers them all at import -- so one floor read in a
pre-push session billed the whole registry, and the empty-tree proof read a floor it did not need.

Measured on 210 declarations: 17,905 ``ast.parse`` calls over 5,171 distinct texts and 152 ``git
ls-files`` calls costing 2.9s of 138s, so the cost is per-guard parsing, not the enumeration; sharing
one enumeration across declarations would have saved about 2%. What is shared instead is the base
process: one per module asked about, or one for the whole registry via ``prefetch_base``.

The measurement is replaced by a recorder here, so these cases cost nothing and a regression shows as a
count rather than as a slow run. Each has a control that proves the recorder sees a real measurement.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests import _reach, _reach_base
from repo_tests._reach import Reach, ReachFloorError
from repo_tests.audio_extension_allowlist_test import REACH as REAL

_POPULATION = 10


def _decl(name: str, module: str, found: int = 3) -> Reach[int]:
    return Reach(name=name, discover=lambda _root: list(range(found)), pinned_floor=0, what="x", module=module)


@pytest.fixture
def walks(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Replace the base walk with a recorder: each entry is the declaration names one walk covered."""
    seen: list[list[str]] = []

    def record(reaches: list[Reach]) -> None:
        seen.append(sorted(r.name for r in reaches))
        _reach_base._BASE_COUNT.update({r.name: _POPULATION for r in reaches})

    registry = {
        r.name: r
        for r in (_decl("w::a1", "mod_a"), _decl("w::a2", "mod_a"), _decl("w::b1", "mod_b"), _decl("w::c1", "mod_c"))
    }
    monkeypatch.setattr(_reach_base, "_measure_at_base", record)
    monkeypatch.setattr(_reach_base, "_BASE_COUNT", {})
    monkeypatch.setattr(_reach_base, "_BASE_FAILED", {})
    monkeypatch.setattr("repo_tests._reach.REGISTRY", registry)
    return seen


def test_reading_one_floor_walks_only_its_own_module(walks: list[list[str]]) -> None:
    from repo_tests._reach import REGISTRY  # noqa: PLC0415 - the patched registry

    assert REGISTRY["w::a1"].floor == _POPULATION
    assert walks == [["w::a1", "w::a2"]], "a floor read walked more than the module that declares it"
    assert REGISTRY["w::a2"].floor == _POPULATION
    assert len(walks) == 1, "a sibling in an already-measured module was walked a second time"


def test_walks_never_exceed_the_distinct_modules_asked_about(walks: list[list[str]]) -> None:
    from repo_tests._reach import REGISTRY  # noqa: PLC0415

    asked = ["w::a1", "w::b1", "w::a2", "w::a1", "w::b1"]
    for name in asked:
        _ = REGISTRY[name].floor
    modules = {REGISTRY[name].module for name in asked}
    assert len(walks) == len(modules) == 2, f"{len(walks)} walks for {len(modules)} distinct modules: {walks}"
    assert not any("w::c1" in walk for walk in walks), "a module nobody asked about was walked"


def test_prefetch_is_one_walk_for_the_whole_registry(walks: list[list[str]]) -> None:
    from repo_tests._reach import REGISTRY  # noqa: PLC0415

    _reach_base.prefetch_base()
    for reach in REGISTRY.values():
        _ = reach.floor
    assert walks == [["w::a1", "w::a2", "w::b1", "w::c1"]], "prefetch must be one walk and leave nothing to re-measure"


def test_an_empty_tree_is_refused_without_reading_any_floor(walks: list[list[str]]) -> None:
    empty = _decl("w::empty", "mod_e", found=0)
    with pytest.raises(ReachFloorError, match="every floor is above zero"):
        empty.examined(Path("."))
    assert walks == [], "the empty-tree proof measured the base, which it has no need of"


def test_control_a_populated_tree_does_read_the_floor(walks: list[list[str]]) -> None:
    """Without this, the empty-tree test above passes if the recorder is simply never reached."""
    _reach_base._BASE_COUNT.clear()
    populated = _decl("w::populated", "mod_p", found=_POPULATION + 2)
    populated.examined(Path("."))
    assert walks == [["w::populated"]]


def test_a_real_declaration_refuses_an_empty_tree_without_a_base_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_reach, "_MEASURED", {})
    monkeypatch.setattr(_reach_base, "_measure_at_base", lambda _r: pytest.fail("the empty-tree proof walked the base"))
    with pytest.raises(ReachFloorError):
        REAL.examined(tmp_path)
