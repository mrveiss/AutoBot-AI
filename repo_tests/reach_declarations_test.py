# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every declared reach floor is proved to fire, mechanically (#15826).

A floor nobody has seen fail is decoration. Tonight produced three guards that
*had* a floor and were still wrong, so "it declares a floor" is not the property
worth measuring — "it fails when it examines nothing" is, and that is
behavioural. This module drives every declaration in `repo_tests/_reach.REGISTRY`
against an empty directory and requires the failure.

Doing it here, once, is the difference between one maintained mutation and 35
hand-written ones that rot. It also makes adoption countable: a guard that has
not declared is invisible to this file, which is what `MIN_DECLARATIONS` is for.
"""

from __future__ import annotations

import importlib
import pkgutil
import subprocess
from pathlib import Path

import pytest

from repo_tests._reach import REGISTRY, Reach, declare

_REPO_TESTS = Path(__file__).resolve().parent

#: A **shrink-guard, not a reach floor.** At the current adoption count this
#: cannot fail until someone *removes* a declaration — which is worth having,
#: since every other guard will hang off this mechanism, but it measures no
#: coverage and must not be read as if it did. Ratchets **up** only, and should
#: be raised as adoption grows or it becomes the thing it was built to prevent.
MIN_DECLARATIONS = 2

#: The only failures that mean "the floor worked" rather than "the guard is broken".
_EXPECTED_ON_EMPTY = (AssertionError, subprocess.CalledProcessError, FileNotFoundError)

#: Guard modules that could not be imported, recorded rather than discarded.
IMPORT_FAILURES: dict[str, str] = {}


def _import_every_guard() -> None:
    """Import every guard module so its `declare(...)` runs.

    Import errors are surfaced, not swallowed: a guard that cannot import is a
    guard that is not running, and this file exists to notice exactly that class
    of silence.
    """
    for module in pkgutil.iter_modules([str(_REPO_TESTS)]):
        if module.name.startswith("_") or module.name == Path(__file__).stem:
            continue
        try:
            importlib.import_module(f"repo_tests.{module.name}")
        except Exception as exc:  # noqa: BLE001 - recorded, never discarded
            IMPORT_FAILURES[module.name] = f"{type(exc).__name__}: {exc}"


_import_every_guard()


def _declarations() -> list[Reach]:
    return sorted(REGISTRY.values(), key=lambda r: r.name)


def test_the_registry_was_actually_populated() -> None:
    """The vacuity floor for this file itself.

    Every assertion below is parametrised over the registry, so an empty
    registry makes all of them pass by having nothing to check — this module
    would then be the exact defect it exists to catch.
    """
    assert len(REGISTRY) >= MIN_DECLARATIONS, (
        f"only {len(REGISTRY)} reach declarations found; expected at least {MIN_DECLARATIONS}. "
        "Either adoption regressed or the import sweep above stopped reaching guard modules."
    )


@pytest.mark.parametrize("reach", _declarations(), ids=lambda r: r.name)
def test_no_guard_can_succeed_against_an_empty_tree(reach: Reach, tmp_path: Path) -> None:
    """The mutation, applied mechanically: point discovery at nothing.

    The property is **it must not return successfully**, but "any exception
    qualifies" is too weak: a `discover` broken by a typo raises too, and this
    suite would then report a dead guard as adopted — the mechanism failing in
    precisely the way it exists to detect.

    So the accepted failures are named. `AssertionError` is the floor doing its
    job; `CalledProcessError` and `FileNotFoundError` are a guard whose discovery
    cannot run against an unusable root (`env-var-bare-cast` shells out to
    `git ls-files` with `check=True`), which is loud *and* distinguishable from a
    defect. Anything else fails the test, which is how this test gets a second
    way to fail rather than only "it did not raise".
    """
    try:
        result = reach.examined(tmp_path)
    except _EXPECTED_ON_EMPTY:
        return
    except BaseException as exc:  # noqa: BLE001 - the point is to name what it was
        pytest.fail(
            f"{reach.name} failed against an empty tree, but with "
            f"{type(exc).__name__}: {exc!r}. That is a broken discovery, not a floor "
            f"doing its job, and accepting it would let a typo read as adoption."
        )

    pytest.fail(f"{reach.name} returned {len(result)} items from an empty tree instead of failing")


@pytest.mark.parametrize("reach", _declarations(), ids=lambda r: r.name)
def test_discovery_honours_the_root_it_is_given(reach: Reach, tmp_path: Path) -> None:
    """The unenforced contract behind every other test here.

    Nothing in `declare(...)` makes `discover` use the root it is handed. A
    `discover=lambda _root: _tracked_files()` closing over the repo returns its
    full sweep against *any* directory, clears its floor unconditionally, and can
    never fail — while passing the empty-tree test above for the wrong reason,
    since it never looked at the empty tree at all.

    Comparing the two results is enough to catch it: the live tree yields at
    least `floor` items and the floor is non-zero, so a discovery that honours
    its argument cannot return the same thing for both. A discovery that
    *raises* on the empty root has also honoured it — it tried to read that
    directory and could not — so those failures satisfy the contract too.
    """
    try:
        from_empty = reach.discover(tmp_path)
    except _EXPECTED_ON_EMPTY:
        return  # it tried to use the root and could not, which is the contract met

    from_repo = reach.discover(_REPO_TESTS.parent)

    assert list(from_empty) != list(from_repo), (
        f"{reach.name} returned identical results for an empty directory and the "
        f"repository, so its discovery ignores the root it is given. A floor it "
        f"clears unconditionally measures nothing."
    )


@pytest.mark.parametrize("reach", _declarations(), ids=lambda r: r.name)
def test_each_declared_floor_is_cleared_by_the_live_tree(reach: Reach) -> None:
    """The other direction: a floor set above the tree fails every honest run."""
    found = reach.examined(_REPO_TESTS.parent)

    assert len(found) >= reach.floor


@pytest.mark.parametrize("reach", _declarations(), ids=lambda r: r.name)
def test_no_floor_sits_at_zero(reach: Reach) -> None:
    """A floor of zero is satisfied by discovering nothing, which is the state
    it exists to reject."""
    assert reach.floor > 0, f"{reach.name} declares a floor of {reach.floor}"


def test_a_floor_that_cannot_fail_is_rejected_by_this_suite() -> None:
    """The contrast for the mutation test itself.

    If `examined` ever stopped raising, every parametrised case above would pass
    silently. This constructs a declaration that discovers nothing and asserts
    the machinery still objects.
    """
    never_finds_anything = declare("self-check::always-empty", discover=lambda root: [], floor=1, what="items")

    with pytest.raises(AssertionError, match="Fix the sweep"):
        never_finds_anything.examined(_REPO_TESTS)

    REGISTRY.pop("self-check::always-empty", None)


def test_no_guard_failed_to_import() -> None:
    """A guard that cannot import is absent from the registry and invisible here.

    The previous version discarded these, and its own docstring claimed the
    opposite — so a guard could break, vanish from the sweep, and leave the
    registry floor satisfied by the guards that still worked (#15826 review).
    That is this file's failure mode reproduced inside this file.
    """
    assert not IMPORT_FAILURES, (
        "these guard modules could not be imported, so their declarations (if any) are missing "
        f"from the registry: {IMPORT_FAILURES}"
    )
