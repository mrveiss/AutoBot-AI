# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A tree-scanning guard must bind a floor to what it examined (#15826).

**A scan of nothing prints the same clean line as a clean tree.** Every guard
here enumerates the repository and asserts something about what it finds; a guard
whose enumeration silently returns empty reports the same green as one that
looked at everything and found no offenders. Nothing distinguishes them, and a
silent wrong answer outlives every loud one.

``repo_tests/_reach.py`` already answers this with :func:`declare`, and
``reach_declarations_test`` already proves declared floors fire — including
against a genuinely empty repository. What did not exist is the thing that makes
adoption non-optional: **a check that fails when a new tree-scanning guard
arrives with no floor at all.** This is that check.

WHAT THIS MEASURES, AND WHAT IT CANNOT SEE
------------------------------------------
Population: tracked ``repo_tests/*_test.py`` whose source contains an
enumerator — ``tracked_paths``, ``git ls-files``, ``rglob(``, ``os.walk(`` or
``.iterdir(``. Stated because a narrow scope is not the defect; an **undeclared**
one is.

Four boundaries a reader should not have to discover:

* **Only ``repo_tests/``.** 301 tracked ``.py`` files repo-wide carry an
  enumerator — 13 in ``scripts/``, 32 in ``tools/``, 8 in ``pipeline-scripts/``,
  32 under ``autobot-infrastructure/``. Those are out of scope here and are
  **not** covered by any equivalent check.
* **Only ``*_test.py``.** Helper modules in this directory (``*_scan.py``,
  ``*_flow.py``, ``*_guard.py``) enumerate on behalf of a caller that may hold
  the floor, so requiring one of the helper would be wrong. Six such modules
  currently have no floor of their own and are invisible to this check.
* **Floor detection is syntactic.** A floor expressed in a way this module's
  AST walk does not recognise reads as absent. That fails toward false
  positives, which is the safe direction: the remedy is a `GRANDFATHERED`
  entry, which is a decision someone writes down.
* **A floor's *value* is not judged here.** ``reach_declarations_test`` proves a
  declared floor is non-zero and cleared by the live tree; an ad-hoc floor of 1
  passes this check while being nearly worthless. Presence, not adequacy.

THE GRANDFATHERED LIST SHRINKS ONLY, AND FAILS IN BOTH DIRECTIONS
-----------------------------------------------------------------
An unrecorded *shrink* is as much a defect as growth: if a guard gains a floor
and nobody removes its entry, the list silently permits the next guard to lose
one. Same shape as an allowance the scanner has stopped reporting.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from repo_tests._paths import repo_root  # noqa: E402

from tools.lint._scan_helpers import tracked_paths  # noqa: E402

#: What counts as enumerating the tree.
#:
#: ``.glob(`` was missing until #16147, and its absence was the same defect this
#: module exists to catch, one level up: the sweep reported every guard compliant
#: while 21 tree-scanning guards were outside the set it read. A blind spot in a
#: detector is indistinguishable from a clean result, which is why the floor below
#: is bound to guards EXAMINED rather than to guards found wanting.
#:
#: ``.glob(`` is listed after ``rglob(`` deliberately -- ``rglob`` contains no
#: literal ``.glob(``, so the two are independent alternatives rather than one
#: subsuming the other.
_ENUMERATOR = re.compile(r"tracked_paths|ls-files|rglob\(|os\.walk\(|\.iterdir\(|\.glob\(")

#: Bound to guards EXAMINED, never to guards found wanting. A `git ls-files`
#: returning nothing would otherwise pass this module having read zero guards --
#: the exact failure it exists to catch, inside itself.
#:
#: MEASURED 2026-09-10 against `origin/main`: 201 tracked
#: `repo_tests/*_test.py`, of which 101 matched `_ENUMERATOR` (80 before
#: `.glob(` was added, 21 reachable only through it). The previous value of 60
#: sat 20 below the then-current 80 and 41 below the true population, so it
#: could not have fired on the very blind spot #16147 reports.
#:
#: RE-MEASURED 2026-09-11: 104 tracked `repo_tests/*_test.py` match
#: `_ENUMERATOR` -- 3 more than the day before. #16147 AC1 (option A): pin the
#: floor to the exact measured count instead of trailing it by roughly 6%,
#: since that gap was the blind spot #16147 was filed for. A legitimate guard
#: removal now needs a same-PR floor lowering, same as every other reach
#: floor in this module (#15928).
#:
#: RE-MEASURED 2026-09-19 on the ws-auth train (#17048): 273 tracked
#: `repo_tests/*_test.py`, 132 match `_ENUMERATOR` and 104 match it without
#: `.glob(`. Guard growth had carried the no-`.glob(` reach up to the old floor
#: of 104, so dropping the term no longer failed anything -- re-pinned to the
#: exact full reach so the mutation below fires again.
#: RE-MEASURED 2026-09-29 on the pinning-guard train (#17804): 165 tracked
#: `repo_tests/*_test.py` match `_ENUMERATOR`, 132 match it without `.glob(`.
#: Ten days of guard growth carried the no-`.glob(` reach from 104 to 131, and
#: this PR's own new guard -- reached via `rglob(`, so it lands in the narrowed
#: set -- made it the 132nd, exactly the old floor. At equality the mutation
#: test below reads as clean while detecting nothing, which is the third time
#: this floor has been caught from below (2026-09-11, 2026-09-19, today).
#:
#: This is maintenance, not a patch: the floor does double duty -- a reach floor
#: on line ~257 and, on line ~355, the yardstick for whether that floor could
#: still notice a lost enumerator term. The second job is only healthy while the
#: number tracks full reach, so growth in the narrowed reach silently eats the
#: detection margin and the pin has to be re-measured.
#:
#: Every count above is files MATCHING `_ENUMERATOR`, not guards that scan the
#: tree: a match can be incidental. CENSUS 2026-10-02 at 168 matched (#15826),
#: each of the 33 `.glob(`-only members resolved by chasing its receiver's
#: binding, not its name: 30 true, 3 false, 0 unresolved --
#: `hook_self_sync_atomic_test` and `prepush_hook_sync_17578_test` glob a
#: `tmp_path`, `sync_to_slm_db_update_classify_14459_test` globs the host
#: filesystem. True tree-scanning population: 165, exactly this floor. The
#: apparent 3 of headroom ARE the 3 false members, so there is no real margin,
#: and tightening `.glob(` to exclude them lands at equality -- it needs a floor
#: decision in the same change. Quote these numbers as "matched", never as
#: "guards examined", and never quote 168 - 165 as margin.
#:
#: Do NOT "fix" the treadmill by deriving this from the tree. A floor computed
#: by the same enumerator it guards always agrees with itself and can never
#: fail; the hand-pinned number is the whole mechanism, and paying it forward on
#: each guard change is the cost of having a check that can fail.
MIN_GUARDS_EXAMINED = 165

#: WHAT THIS MODULE CHECKS, AND WHAT IT DOES NOT (#16154).
#:
#: This asks whether a floor **exists**. Whether that floor can actually **fire**
#: is a different question, answered by `reach_declarations_test`, which hands
#: every declaration an empty repository and requires it to raise.
#:
#: The two ask different questions, and NEITHER is reliably in the pre-push set:
#: `tools/git-hooks/pre-push` selects tests by changed-file match and directory
#: sibling, so a meta-test runs only when it is itself in the diff. An earlier
#: version of this comment claimed this module was always in that set; the hook
#: does not say so, and the claim was removed rather than left to be trusted.
#: So a floor that exists but cannot fire --
#: because its `discover` raises on an empty tree instead of returning [] --
#: passes pre-push and fails in CI, which is the slowest possible place to learn
#: it. Stating the gap here rather than implying full coverage: an author who
#: reads this module and sees "reach is checked" will not go looking for the
#: half that is not checked until it is pushed.
#:
#: `_reach.declare` documents the empty-tree contract at the point an author
#: writes a `discover`, and `_reach.Reach.examined` raises `ReachDiscoveryError`
#: naming a raising `discover` as the cause rather than letting a bare traceback
#: read as a broken guard.

#: Tree-scanning `*_test.py` guards with no floor of any kind, frozen so a NEW
#: one fails. May only shrink, and a shrink must be recorded here.
GRANDFATHERED = frozenset(
    {
        "repo_tests/fixture_fixed_path_teardown_guard_gating_test.py",
        # Entered the examined set with `.glob(` (#16147). It was always a
        # tree-scanning guard with no floor; it was simply invisible to the
        # detector. Recorded here rather than fixed in the same change, so the
        # enumerator widening is reviewable on its own -- the alternative is a
        # diff where a detector change and a guard change explain each other.
        "repo_tests/promtool_rules_test.py",
        "repo_tests/workflow_planner_deprecation_test.py",
    }
)

#: GRANDFATHERED as last recorded -- a mirrored second copy (#16147 AC4), the
#: same two-copy shape as the file-size ratchet's RATCHET_BASELINE. The staleness
#: test forces removals; without this copy, ADDING an entry to GRANDFATHERED
#: silences a new unfloored guard and no test fails. Growing the list now takes
#: editing both sets -- a recorded decision a reviewer sees -- and a shrink is
#: mirrored here too, so a removed entry cannot quietly come back.
_GRANDFATHERED_BASELINE = frozenset(
    {
        "repo_tests/fixture_fixed_path_teardown_guard_gating_test.py",
        "repo_tests/promtool_rules_test.py",
        "repo_tests/workflow_planner_deprecation_test.py",
    }
)


#: A name that reads as a floor: ``MIN_FILES``, ``_FLOOR``, ``budget.min_files``,
#: ``minimum_reach``. Case-insensitive because a floor's name is a convention,
#: not its reach -- the case-sensitive form read
#: ``background_task_retention_ratchet_test``'s ``budget.min_files`` as no floor
#: at all. Bounded by ``_`` or end so ``minutes`` and ``mine`` do not qualify,
#: and never applied to a call target, so the builtin ``min(...)`` and
#: ``math.floor(...)`` do not either.
_FLOOR_NAME = re.compile(r"_?(min|floor)(imum)?(_|$)", re.IGNORECASE)


def _names_a_floor(node: ast.AST, call_targets: set[int]) -> bool:
    if id(node) in call_targets:
        return False
    if isinstance(node, ast.Name):
        return bool(_FLOOR_NAME.match(node.id))
    if isinstance(node, ast.Attribute):
        return bool(_FLOOR_NAME.match(node.attr))
    return False


def _compares_a_floor_to_reach(compare: ast.Compare, call_targets: set[int]) -> bool:
    """A floor name counts only when compared against something that is not a constant.

    ``files_parsed >= budget.min_files`` binds a measured reach to the floor;
    ``budget.min_files > 0`` checks the configured bound and examines nothing.
    """
    operands = [compare.left, *compare.comparators]
    for i, operand in enumerate(operands):
        if any(_names_a_floor(n, call_targets) for n in ast.walk(operand)):
            others = operands[:i] + operands[i + 1 :]
            if any(not isinstance(o, ast.Constant) for o in others):
                return True
    return False


def _assert_binds_a_floor(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return True
    nodes = list(ast.walk(test))
    call_targets = {id(n.func) for n in nodes if isinstance(n, ast.Call)}
    for inner in nodes:
        if isinstance(inner, ast.Call) and getattr(inner.func, "id", "") == "len":
            return True
        if isinstance(inner, ast.Compare) and _compares_a_floor_to_reach(inner, call_targets):
            return True
    return False


def has_floor(source: str) -> bool:
    """Does this source bind an assertion to how much it examined?

    Two accepted forms. ``repo_tests._reach.declare`` is canonical and is what
    ``reach_declarations_test`` can prove. An ad-hoc ``assert len(found) >= N``
    is the older form the migration is moving away from, and counts: this check
    asks whether a floor exists, not whether it is the preferred one.
    """
    if re.search(r"\bdeclare\s*\(", source) and "_reach" in source:
        return True
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return True  # unparsed: not this check's finding to report
    return any(isinstance(node, ast.Assert) and _assert_binds_a_floor(node.test) for node in ast.walk(tree))


def _tracked_guards() -> list[Path]:
    """Enumerated through the canonical helper (#15926), not a direct git call.

    `tracked_paths` lets **git** do the pathspec matching, so the filter and the
    returned paths cannot disagree -- which is what #15510 cost when an
    exclusion was tested against the absolute path.
    """
    root = repo_root()
    return [root / rel for rel in tracked_paths(root, "repo_tests/*_test.py")]


def _scanning_guards() -> dict[str, bool]:
    """Relative path -> whether it binds a floor, for guards that enumerate."""
    root = repo_root()
    found = {}
    for path in _tracked_guards():
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _ENUMERATOR.search(source):
            found[path.relative_to(root).as_posix()] = has_floor(source)
    return found


def test_the_detector_finds_a_floor_it_is_shown() -> None:
    """Known positive, against a REAL guard rather than a synthetic string.

    `audio_extension_allowlist_test.py` declares `floor=5100` through
    `_reach.declare`. A detector that stops recognising it has silently stopped
    working, and every count below would then read as a catastrophe.
    """
    source = (repo_root() / "repo_tests" / "audio_extension_allowlist_test.py").read_text(encoding="utf-8")
    assert has_floor(source), "detector no longer recognises a declared reach floor"


def test_the_detector_fails_a_real_guard_with_its_floor_removed() -> None:
    """The contrast pair, and the criterion #15826 asks for by name.

    A meta-guard that cannot fail on the thing it exists for IS the defect it is
    checking for. So take a REAL guard, remove its floor, and require the
    detector to call it unfloored.

    The removal is done on the AST and unparsed back, rather than by deleting
    lines. Line-deletion leaves the source unparseable, and `has_floor` treats
    unparseable as floored -- so a text-stripped fixture passes this test for
    the wrong reason, which is precisely the failure mode of the thing being
    built. That is not a hypothetical: it is what the first version did.
    """
    source = (repo_root() / "repo_tests" / "audio_extension_allowlist_test.py").read_text(encoding="utf-8")
    assert has_floor(source), "precondition: the fixture must start with a floor"

    tree = ast.parse(source)

    class _RemoveFloors(ast.NodeTransformer):
        def visit_Assert(self, node: ast.Assert) -> ast.AST | None:
            return None

        def visit_Call(self, node: ast.Call) -> ast.AST:
            self.generic_visit(node)
            if getattr(node.func, "id", "") == "declare" or getattr(node.func, "attr", "") == "declare":
                return ast.Call(func=ast.Name(id="dict", ctx=ast.Load()), args=[], keywords=[])
            return node

    stripped = ast.unparse(ast.fix_missing_locations(_RemoveFloors().visit(tree)))
    ast.parse(stripped)  # the fixture must still be valid Python, or it passes for the wrong reason
    assert not has_floor(stripped), "detector reports a floor in a guard whose floor was removed"


def test_a_floor_named_in_lowercase_is_a_floor() -> None:
    """The convention is not the reach (#15826).

    `background_task_retention_ratchet_test.py` asserts
    ``census.files_parsed >= budget.min_files`` plus per-root floors -- a
    richer reach contract than ``declare`` -- and the case-sensitive detector
    read it as unfloored, so it sat in GRANDFATHERED and the staleness test,
    using the same detector, could never retire it.
    """
    source = (repo_root() / "repo_tests" / "background_task_retention_ratchet_test.py").read_text(encoding="utf-8")
    assert has_floor(source), "a guard asserting `>= budget.min_files` must read as floored"
    for form in ("assert n >= budget.min_files", "assert n >= min_reach", "assert n >= _floor"):
        assert has_floor(form), f"{form!r} names a floor in lowercase"


@pytest.mark.parametrize(
    "lookalike",
    [
        "assert min(xs) > 0",
        "assert math.floor(t) > 0",
        "assert elapsed < minutes",
        "assert owner == mine",
        # a floor checked against a constant is the configured bound, not reach
        "assert budget.min_files > 0",
        "assert MIN_FILES > 0",
    ],
)
def test_a_lookalike_of_a_floor_name_is_not_a_floor(lookalike: str) -> None:
    """The control for the case-insensitive match: it must not buy floors it cannot see.

    ``min`` and ``floor`` are also a builtin, a ``math`` function and the stem
    of ordinary words. None of them binds an assertion to how much was examined.
    """
    assert not has_floor(lookalike), f"{lookalike!r} is not a floor"


def _is_emptiness_check(test: ast.expr) -> bool:
    """``len(x) == 0``, ``<= 0``, ``< 1`` or ``not len(x)``: says nothing about reach."""
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return isinstance(test.operand, ast.Call) and getattr(test.operand.func, "id", "") == "len"
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1):
        return False
    left, op, right = test.left, type(test.ops[0]), test.comparators[0]
    if _is_len_call(right) and not _is_len_call(left):  # `0 == len(x)` reads as `len(x) == 0`
        left, right, op = right, left, _MIRRORED.get(op, op)
    if not (_is_len_call(left) and isinstance(right, ast.Constant)):
        return False
    return (op, right.value) in {(ast.Eq, 0), (ast.LtE, 0), (ast.Lt, 1)}


_MIRRORED = {ast.Lt: ast.Gt, ast.Gt: ast.Lt, ast.LtE: ast.GtE, ast.GtE: ast.LtE}


def _is_len_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and getattr(node.func, "id", "") == "len"


def floored_only_by_emptiness(source: str) -> bool:
    """True when every floor ``has_floor`` sees is an assertion that something is EMPTY.

    ``has_floor`` counts any ``len()`` inside an assert, so ``assert
    len(violations) == 0`` reads as a floor while proving nothing was examined.
    Pinned by the sweep below rather than changed in ``has_floor``: measured
    2026-10-02, no tracked guard is in this state, so this is a gap with zero
    instances, not a live defect.
    """
    if not has_floor(source):
        return False

    class _DropEmptiness(ast.NodeTransformer):
        def visit_Assert(self, node: ast.Assert) -> ast.AST | None:
            # `pass`, not removal: dropping the only statement of a function leaves an
            # empty body, the unparse is invalid Python, and has_floor reads a
            # SyntaxError as floored -- the sweep would go blind on exactly that shape.
            return ast.Pass() if _is_emptiness_check(node.test) else node

    stripped = ast.unparse(ast.fix_missing_locations(_DropEmptiness().visit(ast.parse(source))))
    return not has_floor(stripped)


def test_no_guard_is_floored_only_by_an_emptiness_assertion() -> None:
    """Catches the first guard whose only "floor" is ``assert len(found) == 0``."""
    root = repo_root()
    offenders = sorted(
        name
        for name, floored in _scanning_guards().items()
        if floored and floored_only_by_emptiness((root / name).read_text(encoding="utf-8"))
    )
    assert not offenders, "guards whose only floor asserts emptiness -- bind a real floor:\n  " + "\n  ".join(offenders)


def test_the_emptiness_sweep_finds_a_planted_guard() -> None:
    """The sweep above must be able to fail, or it is the defect it checks for."""
    assert floored_only_by_emptiness("found = scan()\nassert len(found) == 0")
    assert floored_only_by_emptiness("found = scan()\nassert not len(found)")
    assert not floored_only_by_emptiness("found = scan()\nassert len(found) == 0\nassert len(seen) >= 50")
    # The emptiness assert as the only statement of a test function -- the shape a
    # real guard takes, and the one a stripped-to-empty body used to hide.
    assert floored_only_by_emptiness("def test_x():\n    assert len(scan()) == 0")
    # The same emptiness written with len() on the right.
    assert floored_only_by_emptiness("found = scan()\nassert 0 == len(found)")
    assert floored_only_by_emptiness("found = scan()\nassert 1 > len(found)")


def test_the_sweep_examined_enough_guards_to_mean_anything() -> None:
    """Non-vacuity, bound to guards EXAMINED rather than guards found wanting."""
    guards = _scanning_guards()
    assert len(guards) >= MIN_GUARDS_EXAMINED, (
        f"examined {len(guards)} tree-scanning guards, floor is {MIN_GUARDS_EXAMINED}. "
        "A sweep over an empty set reports the same clean result as a compliant tree."
    )


def test_no_new_tree_scanning_guard_lacks_a_floor() -> None:
    """The constraint."""
    unfloored = {name for name, floored in _scanning_guards().items() if not floored}
    new = sorted(unfloored - GRANDFATHERED)
    assert not new, (
        "tree-scanning guard(s) with no reach floor:\n  "
        + "\n  ".join(new)
        + "\n\nBind one with repo_tests._reach.declare(...), so an empty enumeration "
        "fails instead of reporting the same green as a clean tree."
    )


def test_the_grandfathered_list_has_not_gone_stale() -> None:
    """The other direction, and the one that is normally forgotten.

    An entry that no longer matches means a guard gained a floor and nobody
    recorded it -- and a list carrying dead entries silently permits the next
    guard to lose one. Same shape as an allowance the scanner has stopped
    reporting.
    """
    unfloored = {name for name, floored in _scanning_guards().items() if not floored}
    stale = sorted(GRANDFATHERED - unfloored)
    assert (
        not stale
    ), "GRANDFATHERED entries that now have a floor -- remove them, the list only shrinks:\n  " + "\n  ".join(stale)


def _grown(current: frozenset[str]) -> list[str]:
    return sorted(current - _GRANDFATHERED_BASELINE)


def test_the_grandfathered_list_never_grows_silently() -> None:
    """#16147 AC4: the list only shrinks, and it is compared as a SET.

    A count would pass one entry swapped for another; the set difference in each
    direction is the assertion worth making (RATCHET_BASELINES.md, rule 4).
    """
    grown = _grown(GRANDFATHERED)
    assert not grown, (
        "GRANDFATHERED gained entries missing from _GRANDFATHERED_BASELINE -- a new "
        "tree-scanning guard needs a floor, not an exemption:\n  " + "\n  ".join(grown)
    )
    unmirrored = sorted(_GRANDFATHERED_BASELINE - GRANDFATHERED)
    assert not unmirrored, (
        "entries removed from GRANDFATHERED but not from _GRANDFATHERED_BASELINE -- mirror "
        "the shrink, or a removed exemption can quietly return:\n  " + "\n  ".join(unmirrored)
    )


def test_the_growth_check_finds_an_added_entry() -> None:
    """Known positive (rule 6): the check must see an addition before its silence means anything."""
    assert _grown(GRANDFATHERED | {"repo_tests/planted_unfloored_guard_test.py"}) == [
        "repo_tests/planted_unfloored_guard_test.py"
    ]


def _examined_with(pattern: re.Pattern[str]) -> set[str]:
    """Guards a given enumerator pattern reaches. Used to mutate the detector."""
    root = repo_root()
    reached = set()
    for path in _tracked_guards():
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if pattern.search(source):
            reached.add(path.relative_to(root).as_posix())
    return reached


def test_dropping_glob_from_the_enumerator_breaks_the_sweep() -> None:
    """#16147 mutation: the `.glob(` alternative must be load-bearing.

    A detector term that changes nothing when removed is decoration, and this
    module cannot tell decoration from coverage by reading itself. So remove the
    term and require the sweep to notice.

    Measured 2026-09-10: 101 guards reached with `.glob(`, 80 without -- and 80
    is below `MIN_GUARDS_EXAMINED`, so a regression that dropped the term would
    fail loudly rather than quietly reading 21 fewer guards.

    This is the check that the previous floor of 60 could not perform: at 60,
    dropping `.glob(` left 80 examined, comfortably above the floor, and the
    sweep reported the same clean result over a fifth fewer guards.
    """
    without_glob = re.compile(_ENUMERATOR.pattern.replace(r"|\.glob\(", ""))
    assert without_glob.pattern != _ENUMERATOR.pattern, "the mutation did not change the pattern"

    full = _examined_with(_ENUMERATOR)
    narrowed = _examined_with(without_glob)

    assert narrowed < full, "removing `.glob(` reached the same guards -- the term is decoration"
    assert len(narrowed) < MIN_GUARDS_EXAMINED, (
        f"removing `.glob(` still reaches {len(narrowed)} guards, at or above the floor of "
        f"{MIN_GUARDS_EXAMINED}. The floor cannot detect the loss, so it is not protecting "
        "the extension -- raise it or the mutation is unguarded."
    )


def test_glob_reaches_guards_no_other_term_does() -> None:
    """The positive half: `.glob(` is not merely redundant with `rglob(`.

    `rglob` contains no literal `.glob(`, so the two are independent — but that
    is an argument, and this asserts it against the tree instead. Named guards
    rather than a count, because a count can be satisfied by any 21 files.
    """
    without_glob = re.compile(_ENUMERATOR.pattern.replace(r"|\.glob\(", ""))
    only_via_glob = _examined_with(_ENUMERATOR) - _examined_with(without_glob)

    assert "repo_tests/promtool_rules_test.py" in only_via_glob
    assert "repo_tests/workflow_concurrency_guard_test.py" in only_via_glob


def test_a_raising_discover_is_named_as_the_cause_not_a_bare_traceback() -> None:
    """#16154: "the sweep is broken" and "the tree is small" are different states.

    A `discover` that raises on an empty tree used to surface as whatever
    exception it threw -- an `EmptyEnumeration`, a `FileNotFoundError` -- which
    reads as a broken guard rather than as the specific, documented contract
    violation it is. `reach_declarations_test` then ends early having proven
    nothing, and the floor it was checking is untested while looking checked.
    """
    from repo_tests._reach import Reach, ReachDiscoveryError, ReachFloorError

    def _raises(_root):
        raise RuntimeError("enumeration exploded")

    reach = Reach(name="synthetic", discover=_raises, floor=1, what="things")

    with pytest.raises(ReachDiscoveryError) as caught:
        reach.examined(repo_root())

    message = str(caught.value)
    assert "RuntimeError" in message, "the original exception type must survive into the message"
    assert "must return an empty sequence" in message or "empty" in message
    assert "excluded_tree_size_debt_test" in message, "must point at the handling it expects"
    assert not isinstance(
        caught.value, ReachFloorError
    ), "a broken sweep must not present as a floor breach -- they call for opposite fixes"


def test_a_floor_breach_is_still_a_floor_error() -> None:
    """The control: wrapping discover must not swallow the ordinary case.

    A change that turned every failure into `ReachDiscoveryError` would pass the
    test above and destroy the distinction it exists to draw.
    """
    from repo_tests._reach import Reach, ReachFloorError

    reach = Reach(name="synthetic-floor", discover=lambda _root: [], floor=5, what="things")

    with pytest.raises(ReachFloorError):
        reach.examined(repo_root())
