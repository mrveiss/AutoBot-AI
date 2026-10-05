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

WHAT A NEW `declare()` COSTS, WHERE THE AUTHOR WILL SEE IT (#17810)
-------------------------------------------------------------------
This file walked the REAL tree twice per declaration and reached 73% of the 214s pre-push
budget, billed to pushes that had added no declaration. The live-tree half now carries the
`reach_floor` marker, which `tools/git-hooks/pre-push` deselects and CI does not -- both ends
asserted below, since a marker nothing selects is a check that runs nowhere. A declaration
still costs three cases against an EMPTY repository at pre-push, and a full tree walk in CI.

Measured on `baec13de40`, one machine, one interpreter, declaration count beside each figure
so the scaling is readable rather than inferred -- re-measure rather than trusting it:

    before, whole file            57 declarations   295 tests   62.07s
    after,  whole file (CI)       58 declarations   357 tests   30.87s
    after,  -m "not reach_floor"  58 declarations   183 tests   10.11s
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import re
import subprocess
import sys
from pathlib import Path

import pytest
from repo_tests._reach import REGISTRY, Reach, ReachFloorError, declare
from repo_tests._reach_policy import ALLOWANCE_VERDICTS, UNSCOPED

from autobot_shared.paths import scrubbed_git_env

_REPO_TESTS = Path(__file__).resolve().parent
_REPO_ROOT = _REPO_TESTS.parent

#: A **shrink-guard, not a reach floor.** At the current adoption count this
#: cannot fail until someone *removes* a declaration — which is worth having,
#: since every other guard will hang off this mechanism, but it measures no
#: coverage and must not be read as if it did. Ratchets **up** only, and should
#: be raised as adoption grows or it becomes the thing it was built to prevent.
MIN_DECLARATIONS = 4


def _scrubbed_env() -> dict[str, str]:
    """`git grep` with the ambient git env removed (#15926 discipline)."""
    return {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GIT_DIR"))}


#: Guard modules that could not be imported, recorded rather than discarded.
IMPORT_FAILURES: dict[str, str] = {}


def _declaring_modules_outside_repo_tests() -> list[str]:
    """Import paths of modules that call `declare(...)` and do not live here.

    Discovered with `git grep`, not enumerated: an enumeration is exactly what
    this file distrusts everywhere else, and a declaration added under a new
    path tomorrow must be swept without anyone remembering to edit a list.

    Why this is needed (#17144, #17298): `declare(...)` registers into a shared
    REGISTRY as an *import side effect*, and the loop below imports only modules
    under `repo_tests/`. A declaration living elsewhere reached the registry
    only when some other test in the same pytest session happened to import its
    module first -- true in CI's whole-suite run, false under
    `pytest repo_tests/`, where the parametrisation dropped from 36 floors to 35
    and reported a clean pass over the smaller set. Not a weaker check: a check
    of a DIFFERENT set, reported identically. It produced a real wrong answer
    today -- a floor re-pinned against a local run that had never examined it.
    """
    out = subprocess.run(
        ["git", "grep", "-lE", r"(^|\s)declare\(", "--", "*.py"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )
    modules = []
    for rel in out.stdout.splitlines():
        if not rel:
            continue
        path = Path(rel)
        if path.parts[0] == "repo_tests":
            continue
        modules.append(".".join(path.with_suffix("").parts))
    return sorted(modules)


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

    # Declarations that live outside this package (#17144, #17298). Same
    # recording discipline: one that cannot be imported is NAMED in
    # IMPORT_FAILURES rather than quietly missing from the sweep.
    for dotted in _declaring_modules_outside_repo_tests():
        if dotted in sys.modules:
            continue
        try:
            importlib.import_module(dotted)
        except Exception as exc:  # noqa: BLE001 - recorded, never discarded
            IMPORT_FAILURES[dotted] = f"{type(exc).__name__}: {exc}"


_import_every_guard()


#: Declarations this suite's own cases create to prove a rule can fire. Excluded from every
#: sweep over the registry: they are fixtures, and counting them would make the frozen sets
#: below depend on which test ran first.
_SELF_CHECK = "self-check::"


def _live() -> dict[str, Reach]:
    """The registry without this suite's own fixtures."""
    return {name: r for name, r in REGISTRY.items() if not name.startswith(_SELF_CHECK)}


def _declarations() -> list[Reach]:
    return sorted(_live().values(), key=lambda r: r.name)


def test_declarations_outside_this_package_are_swept() -> None:
    """A `repo_tests/`-only run must check the same floors CI checks (#17144).

    The floor tests below are parametrised over `REGISTRY`, which `declare(...)`
    fills as an import side effect. Before #17298 the sweep imported only
    modules under `repo_tests/`, so a declaration living elsewhere entered the
    registry only when another test in the same session had already imported its
    module: 36 floors in CI's whole-suite run, 35 under `pytest repo_tests/`,
    and the smaller set reported exactly like the full one.

    This asserts the discovery half rather than a count, because a count would
    have to be edited every time a declaration is added and would then be
    satisfied by editing it. What must hold is that each module found outside
    this package actually contributed: discovered, imported, and present.
    """
    outside = _declaring_modules_outside_repo_tests()

    assert outside, (
        "no declaring module found outside repo_tests/ — either they all moved in here (fine, "
        "delete this test and say so) or the git-grep discovery has stopped matching, in which "
        "case the sweep is silently back to checking a subset"
    )
    assert not [
        m for m in outside if m in IMPORT_FAILURES
    ], "declaring module(s) found but not importable, so their floors are not being checked:\n  " + "\n  ".join(
        f"{m}: {IMPORT_FAILURES[m]}" for m in outside if m in IMPORT_FAILURES
    )


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

    Asserted as **"the empty tree yields nothing"**, not as "the two results differ" (#17810).
    The two forms catch the same defect -- a discovery closing over the repository returns its
    full sweep here -- and only one of them pays for a walk of the real tree. This file was
    73% of the pre-push budget and this test was half of that cost, because it called
    `discover` directly and so bypassed the memo every other test here shares.

    What the comparison bought and this does not: proof that the LIVE result is non-empty, so
    the inequality is not satisfied by both sides being empty. That half is
    `test_each_declared_floor_is_cleared_by_the_live_tree`, which asserts a non-zero floor
    against the real tree and now runs in CI under the `reach_floor` marker. Stated rather than
    dropped: on a pre-push run this case alone cannot tell "honours its root" from "discovers
    nothing anywhere".

    Run against a real empty repository rather than a bare directory, so a git-backed sweep
    produces an empty result instead of an exception that ends the test early.
    """
    from_empty = list(reach.discover(empty_repo))

    assert not from_empty, (
        f"{reach.name} returned {len(from_empty)} item(s) from an EMPTY repository "
        f"(e.g. {from_empty[:3]}), so its discovery does not honour the root it is given -- "
        f"it closes over the repository, or reads the host. A floor it clears unconditionally "
        f"measures nothing."
    )


@pytest.mark.reach_floor
@pytest.mark.parametrize("reach", _declarations(), ids=lambda r: r.name)
def test_each_declared_floor_is_cleared_by_the_live_tree(reach: Reach) -> None:
    """The other direction: a floor set above the tree fails every honest run."""
    found = reach.examined(_REPO_TESTS.parent)

    assert len(found) >= reach.floor


@pytest.mark.parametrize("reach", _declarations(), ids=lambda r: r.name)
def test_no_declaration_can_be_satisfied_by_discovering_nothing(reach: Reach) -> None:
    """Every declaration must bound its sweep from below, by a floor or by a fraction.

    A floor of zero is satisfied by discovering nothing, which is the state it exists to reject.
    Since #17142 a declaration may bound itself RELATIVELY instead -- `min_fraction` against an
    external reference -- and such a declaration carries `floor=0` legitimately, because the
    constant is the thing being removed.

    The property is unchanged and is the one worth asserting: a declaration satisfied by an empty
    sweep asserts nothing. `declare()` refuses the neither-case at construction; this asserts it
    over the live registry, so a declaration that reaches the registry some other way is still
    caught.
    """
    if reach.min_fraction is not None:
        assert (
            0 < reach.min_fraction <= 1
        ), f"{reach.name} declares min_fraction={reach.min_fraction}, which is not a fraction"
        assert not reach.floor and not reach.growth, (
            f"{reach.name} declares min_fraction={reach.min_fraction} alongside floor="
            f"{reach.floor}/growth={reach.growth}; the relative mode does not read them, so a "
            f"reader cannot tell which bound applies"
        )
        return
    assert reach.floor > 0, f"{reach.name} declares a floor of {reach.floor} and no min_fraction"


def test_a_floor_that_cannot_fail_is_rejected_by_this_suite() -> None:
    """The contrast for the mutation test itself.

    If `examined` ever stopped raising, every parametrised case above would pass
    silently. This constructs a declaration that discovers nothing and asserts
    the machinery still objects.
    """
    # Annotated because `Reach` is generic now (#16987) and an empty literal gives mypy no
    # element type to infer -- the one call shape the generic cannot resolve on its own.
    never_finds_anything: Reach[object] = declare(
        "self-check::always-empty", discover=lambda root: [], floor=1, what="items"
    )

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


@pytest.mark.reach_floor
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
    # The predicate lives on Reach now (#15928), so the rule belongs to declare()
    # rather than to whoever remembers to enumerate declarations. This test's job
    # is to DISCHARGE that obligation for every declaration -- see
    # test_every_declaration_is_reached_by_this_sweep for the other half, which
    # is what stops an unenumerated declaration from going unchecked.
    reach.verify_floor(_REPO_ROOT)


def test_every_declaration_is_reached_by_this_sweep() -> None:
    """A declaration this file cannot see has an unchecked floor (#15928).

    `_import_every_guard` walks `pkgutil.iter_modules([_REPO_TESTS])`, which
    reaches top-level `repo_tests` modules and nothing else. A `declare()` in a
    subpackage -- or in `tools/`, or anywhere a future guard lands -- registers
    nothing here, so its floor is never verified and its absence looks identical
    to having no declarations to verify.

    That is the defect this module exists to catch, applied to the module
    itself: the sweep must know what it did not reach.
    """
    # `git grep`, not a Python walk over every file. The walk read ~100 modules
    # per run and pushed the pre-push budget past its 132s ceiling -- and a guard
    # that makes the verification too slow to run is a guard that gets bypassed.
    found = subprocess.run(
        ["git", "grep", "-hoE", r"declare\(\s*[\"']([^\"']+)", "--", "repo_tests/*.py"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        env=_scrubbed_env(),
        check=False,
    )
    declared_names = {
        match.group(1)
        for line in found.stdout.splitlines()
        if (match := re.search(r"""declare\(\s*["']([^"']+)""", line))
    }

    swept = set(REGISTRY) | {name for name in declared_names if name.startswith("self-check::")}
    unreached = sorted(declared_names - swept)

    assert not unreached, (
        "declare() call(s) this sweep never imported, so their floors are unverified:\n  "
        + "\n  ".join(unreached)
        + "\n\n`pkgutil.iter_modules` reaches top-level repo_tests modules only. Either move "
        "the declaration to a top-level module, or widen the import walk -- do not leave it "
        "registered somewhere nothing enumerates."
    )


@pytest.mark.reach_floor
@pytest.mark.parametrize("reach", _declarations(), ids=lambda r: r.name)
def test_every_declared_scope_matches_its_sweep(reach: Reach) -> None:
    """The third coverage state, which nothing used to catch (#17844).

    A guard can be floorless (`guard_reach_meta_test` catches it) or floored below its reach
    (the floor assertion catches it). It can also be floored **correctly, over the wrong
    population** -- and `what=` was free text nobody verified, sitting in the same call as the
    number the framework does verify.

    `roots=` moves the scope into data; this discharges it for every declaration, the same way
    `test_every_declared_floor_is_pinned_to_its_population` discharges `verify_floor`. A
    declaration with no `roots=` is not checked here and is recorded by the test below instead.
    """
    reach.verify_scope(_REPO_ROOT)


def test_the_unscoped_declarations_are_recorded_and_shrinking() -> None:
    """`what=` with no scope is a claim nothing can check, so the set of them only shrinks.

    Compared as a SET in both directions, not by a count: a `<=` ceiling never forces itself
    down, so a declaration gaining `roots=` would have freed a slot for a new bare one with the
    pin still green. RATCHET_BASELINES.md rule 4, applied to the list this change introduces.
    """
    unscoped = {name for name, reach in _live().items() if reach.roots is None}
    added = sorted(unscoped - UNSCOPED)
    assert not added, (
        "declaration(s) with no `roots=` and no entry in repo_tests/_reach_policy.UNSCOPED:\n  "
        + "\n  ".join(added)
        + "\n\nGive it `roots=(...)`. If its discovery does not return paths a prefix can "
        "describe, add it to UNSCOPED and say so -- the list only shrinks, so that is a "
        "recorded decision a reviewer sees, not a default."
    )
    scoped_since = sorted(UNSCOPED - unscoped)
    assert not scoped_since, (
        "UNSCOPED entries whose declaration now carries `roots=` -- remove them, the list only "
        "shrinks and a stale entry quietly permits the next declaration to lose its scope:\n  "
        + "\n  ".join(scoped_since)
    )


def test_every_allowance_carrying_declaration_records_why_it_is_absolute() -> None:
    """A new `growth=` cannot be added without writing down why it is not a fraction (#17914).

    The pattern that produced seventeen re-pins of one guard survives review because no
    individual number in it is wrong. What was missing is the decision: `growth=400` records an
    allowance and records nothing about whether a reference exists that would make the
    allowance unnecessary.

    This does NOT demand conversion. "52 declarations carry an allowance" is not "52 pending
    conversions": most of these populations have no co-moving reference, and a fraction against
    a reference that drifts fires falsely. The verdict table says which, and which are still
    outstanding.
    """
    carrying = {name for name, r in _live().items() if r.min_fraction is None and r.growth}
    missing = sorted(carrying - set(ALLOWANCE_VERDICTS))
    assert not missing, (
        "declaration(s) carrying a `growth` allowance with no recorded verdict in "
        "repo_tests/_reach_policy.ALLOWANCE_VERDICTS:\n  "
        + "\n  ".join(missing)
        + "\n\nRecord ABSOLUTE with the reason a reference cannot co-move with this population, "
        "or CONVERTIBLE and lower MAX_CONVERTIBLE when you convert it."
    )
    stale = sorted(set(ALLOWANCE_VERDICTS) - carrying)
    assert not stale, (
        "ALLOWANCE_VERDICTS entries whose declaration no longer carries an allowance -- remove "
        "them, the table only shrinks:\n  " + "\n  ".join(stale)
    )


def test_a_relative_declaration_whose_population_is_not_the_tree_names_its_own_reference() -> None:
    """#17914 AC3, asserted rather than left to review.

    `tracked_file_count` is the whole tracked tree. A guard bounding a suffix-matched subset and
    borrowing that denominator gets a floor that rises at the TREE's rate while the thing it
    bounds grows at its own -- which is the same mistake in the opposite direction from the
    absolute floor it replaced. The first version of #17142 made exactly this error.

    Expressed as "a relative declaration whose sweep is materially smaller than the tracked
    tree must name a reference", because that is the checkable half: a guard scanning every
    tracked file legitimately borrows the default.
    """
    from repo_tests._reach import tracked_file_count  # noqa: PLC0415

    total = tracked_file_count(_REPO_ROOT)
    assert total > 0, "the tracked-file reference measured nothing; the check below would be vacuous"
    borrowing = sorted(
        name
        for name, reach in _live().items()
        if reach.min_fraction is not None
        and reach.reference is None
        and len(reach.population(_REPO_ROOT)) < total * 0.95
    )
    assert not borrowing, (
        "relative declaration(s) bounding a proper subset of the tracked tree while borrowing "
        "the tracked-file count as their denominator:\n  "
        + "\n  ".join(borrowing)
        + "\n\nName a `reference=` enumerating the same population, as "
        "`hooks_path_override_15961_test._suffix_matched_count` does."
    )
    # Known positive (RATCHET_BASELINES rule 6). The sweep above is clean today, and a clean
    # result from a predicate nothing exercises is this file's own subject: invert the
    # `reference is None` term and it stays green. So drive it with a declaration IN breach.
    planted = Reach(
        name="self-check::borrows-the-tree",
        discover=lambda _root: ["a/x.py"],
        floor=0,
        what="a subset borrowing the tracked-file count",
        min_fraction=0.5,
    )
    assert (
        planted.reference is None and len(planted.population(_REPO_ROOT)) < total * 0.95
    ), "the planted breach is not in breach, so the sweep above cannot be shown to fire"


#: Where the live-tree half of this file is paid, and where it is not (#17810).
_PREPUSH_HOOK = _REPO_ROOT / "tools" / "git-hooks" / "pre-push"
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_FLOOR_MARKER = "reach_floor"


def test_the_live_tree_checks_are_deselected_at_pre_push_and_selected_in_ci() -> None:
    """The split is only real while BOTH halves hold, so both are asserted here (#17810).

    This file was 156.75s of a 214s pre-push budget, and the cost scaled with the number of
    declared floors: every `declare()` made every future push slower, and the author paid
    nothing at the moment of declaring. The empty-tree proof is the half that must run near the
    author -- it is what makes a floor provable at all -- and the floor-versus-population check
    is a ratchet, which is what CI is for.

    A marker that the hook deselects and nothing in CI selects is strictly worse than the cost
    it saves: the check would stop running anywhere and the suite would get faster, which is
    exactly how a guard dies quietly. So this asserts the hook skips the marker AND that CI's
    `-m` expression does not exclude it.
    """
    # The INVOCATION line, not the file. The first version of this assertion searched the whole
    # hook for the flag, and the hook's own explanatory comment quotes it -- so deleting the flag
    # from the command left the check green. A guard satisfied by the prose beside the thing it
    # guards is the exact shape this suite exists to catch, found by mutating it.
    # The trailing comment is STRIPPED, not used to drop the line. Skipping any line
    # containing `#` would have dropped a real invocation that happened to carry a trailing
    # comment -- the same prose-versus-code confusion one step along, reported by review.
    invocations = [
        head
        for head in (line.split("#", 1)[0] for line in _PREPUSH_HOOK.read_text(encoding="utf-8").splitlines())
        if "-m pytest" in head
    ]
    assert invocations, "no uncommented `python -m pytest` invocation found in tools/git-hooks/pre-push"
    unmarked = [line.strip() for line in invocations if f'-m "not {_FLOOR_MARKER}"' not in line]
    assert not unmarked, (
        f"tools/git-hooks/pre-push runs pytest without deselecting `{_FLOOR_MARKER}`, so every "
        f"push pays one full tree walk per declared floor again:\n  " + "\n  ".join(unmarked)
    )

    workflow = _CI_WORKFLOW.read_text(encoding="utf-8")
    selectors = [line for line in workflow.splitlines() if line.strip().startswith("-m ")]
    assert selectors, "no `-m` marker expression found in ci.yml; this check can no longer see what CI selects"
    excluding = [line.strip() for line in selectors if f"not {_FLOOR_MARKER}" in line]
    assert not excluding, (
        f"ci.yml deselects `{_FLOOR_MARKER}`, so the floor-versus-population check now runs "
        f"NOWHERE -- pre-push skips it by design:\n  " + "\n  ".join(excluding)
    )
