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

from autobot_shared.paths import scrubbed_git_env
from repo_tests._reach import REGISTRY, Reach, ReachFloorError, declare

_REPO_TESTS = Path(__file__).resolve().parent
_REPO_ROOT = _REPO_TESTS.parent

#: A **shrink-guard, not a reach floor.** At the current adoption count this
#: cannot fail until someone *removes* a declaration — which is worth having,
#: since every other guard will hang off this mechanism, but it measures no
#: coverage and must not be read as if it did. Ratchets **up** only, and should
#: be raised as adoption grows or it becomes the thing it was built to prevent.
MIN_DECLARATIONS = 2

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


@pytest.fixture
def empty_repo(tmp_path: Path) -> Path:
    """An initialised git repository containing nothing.

    A bare `tmp_path` is not this: a discovery that shells out to `git ls-files`
    fails there with `CalledProcessError` *before* `Reach._require` runs, so the
    test would accept "the sweep could not run" in place of "the floor rejected
    an empty sweep" — proving the guard is loud without proving its floor binds.
    An initialised repository lets the sweep succeed and return nothing, which is
    the case the floor exists for.
    """
    subprocess.run(
        ["git", "init", "--quiet", str(tmp_path)],
        check=True,
        capture_output=True,
        env=scrubbed_git_env(),
    )
    return tmp_path


@pytest.mark.parametrize("reach", _declarations(), ids=lambda r: r.name)
def test_no_guard_can_succeed_against_an_empty_tree(reach: Reach, empty_repo: Path) -> None:
    """The mutation, applied mechanically: point discovery at an empty tree.

    The required failure is **`ReachFloorError` specifically** — the floor
    rejecting a sweep that found nothing. Three weaker rules were tried and each
    let a dead guard read as adopted:

    * "any exception qualifies" accepts a `discover` broken by a typo;
    * "process failures also qualify" accepts a sweep that never ran, because
      `git ls-files` raises `CalledProcessError` on a directory that is not a
      repository — loud, but silent about whether the floor binds;
    * "`AssertionError` qualifies" accepts a discovery that failed its own
      assert before the floor ran — and since the guards this module migrates
      "already express it as `assert len(found) >= _MIN_X`", that is the normal
      case rather than an exotic one.

    The `empty_repo` fixture removes the second case at the source rather than
    excusing it: the sweep runs and returns nothing. `ReachFloorError` removes
    the third by giving the floor a type nothing else raises, so this catch is
    satisfiable only by the floor. Any other exception is a broken guard and
    fails the test.
    """
    try:
        result = reach.examined(empty_repo)
    except ReachFloorError:
        return
    except BaseException as exc:  # noqa: BLE001 - the point is to name what it was
        pytest.fail(
            f"{reach.name} failed against an empty repository, but with "
            f"{type(exc).__name__}: {exc!r}. The floor was never reached, so this "
            f"says the guard is loud and nothing about whether its floor binds."
        )

    pytest.fail(f"{reach.name} returned {len(result)} items from an empty tree instead of failing")


@pytest.mark.parametrize("reach", _declarations(), ids=lambda r: r.name)
def test_discovery_honours_the_root_it_is_given(reach: Reach, empty_repo: Path) -> None:
    """The unenforced contract behind every other test here.

    Nothing in `declare(...)` makes `discover` use the root it is handed. A
    `discover=lambda _root: _tracked_files()` closing over the repo returns its
    full sweep against *any* directory, clears its floor unconditionally, and can
    never fail — while passing the empty-tree test above for the wrong reason,
    since it never looked at the empty tree at all.

    Comparing the two results is enough to catch it: the live tree yields at
    least `floor` items and the floor is non-zero, so a discovery that honours
    its argument cannot return the same thing for both. Run against a real
    empty repository rather than a bare directory, so a git-backed sweep
    produces an empty result to compare instead of an exception that ends the
    test early and proves nothing about the comparison.
    """
    from_empty = reach.discover(empty_repo)
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


@pytest.mark.parametrize("reach", _declarations(), ids=lambda r: r.name)
def test_every_declared_floor_is_pinned_to_its_population(reach: Reach) -> None:
    """A floor far below its population catches only total collapse (#15928).

    `test_no_guard_can_succeed_against_an_empty_tree` proves a floor *fires*.
    It cannot prove the floor is **tight**, and every floor examined in review
    during #15896, #15901 and #15913 fired correctly against an empty tree
    while tolerating the loss of most of a real one.

    Total collapse is not the failure that happens. Partial loss is: a glob
    narrowed, a directory moved, a change propagated to some call sites and not
    others. A floor of 3,000 against 5,241 files detects only the loss of the
    one tree holding 75% of them; the other five can vanish silently. That is
    the shape this asserts against.

    The rule is equality by default -- `growth=0` -- because a floor that sits
    at its population turns any shrinkage into a failure, and shrinking a
    guarded population is exactly the event worth a deliberate line in a diff.
    A population that ordinary work grows declares `growth=N` and says so where
    a reviewer sees it, rather than being pinned low and quietly meaning
    nothing.

    **This measures `discover`, and one floor serves two populations.**
    `examined()` bounds what discovery returned; `completed()` bounds what the
    guard finished, which is lower whenever files are skipped as unreadable or
    unparseable -- 262 of 5,599 for `audio-extension-allowlist`. A floor that
    satisfies this test can still fail the guard's own `completed()` check, and
    the first version of this ratchet did exactly that: the pre-push hook
    rejected it. `skips` now carries that gap under its own name, so `growth`
    means only what it says and each number can be chosen against one quantity.

    So this check is necessary and not sufficient. It catches a floor far below
    its population; `completed()` remains the binding constraint. Giving the
    two populations separate floors is the fuller fix and is not this change.
    """
    count = len(reach.discover(_REPO_ROOT))
    slack = count - reach.floor

    assert slack >= 0, (
        f"[{reach.name}] floor {reach.floor} exceeds the live population of "
        f"{count} {reach.what}. The guard cannot pass; lower the floor to "
        f"{count} only if the population genuinely shrank."
    )
    allowance = reach.skips + reach.growth
    assert slack <= allowance, (
        f"[{reach.name}] floor {reach.floor} sits {slack} below its live "
        f"population of {count} {reach.what}, which exceeds the declared "
        f"allowance of {allowance} (skips={reach.skips} + growth={reach.growth}).\n"
        f"A floor this far below what the sweep finds passes while most of the "
        f"tree stops being reached.\n"
        f"Raise the one that is actually short:\n"
        f"  skips=  items this guard cannot COMPLETE (unreadable, unparseable). "
        f"Measure it from a `completed` failure; do not estimate it.\n"
        f"  growth= ordinary growth tolerated before a deliberate ratchet.\n"
        f"If neither is short, the floor is stale: ratchet it toward {count}."
    )
