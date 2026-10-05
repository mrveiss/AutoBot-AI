# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The census `guard_reach_meta_test` runs on: what counts as an enumerator, and the floor.

Split out of that module when it reached the 600-line ceiling, not because the constants
belong somewhere else: they are read by exactly one caller and the re-pin history below is the
record that makes the floor a decision rather than a number. `reach_floor_migration_test`
excludes this path for the same reason it excludes `guard_reach_meta_test.py` -- #16147 decided
this floor's exact form (a dated, re-measured bare constant, not `declare()`), and relocating
the constant does not reopen that ruling.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

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
#:
#: **STATED LIMITATION: this matches RAW SOURCE TEXT, comments and docstrings included (#17941).**
#: A file that merely QUOTES one of these alternatives in prose joins the population, with no
#: tree-scanning code in it at all. That happened inside this very change: the new
#: ``guard_reach_floor_window_17818_test`` named the glob term once in its module docstring and
#: became a fourth non-scanning member of the population #17870 removes three from. It was
#: caught by a reviewer, not by this module, and the remedy applied was to reword the prose --
#: which is a fix for one file, not for the class.
#:
#: The real fix is a shared "executable lines of this file" helper, which #17941 owns together
#: with seven existing private comment-strippers and #15771. **A stripper written here would be
#: the eighth private copy**, and the repo's one-defect-one-fix rule says the sightings raise
#: that issue's priority rather than its count. So this is recorded as a boundary a reader can
#: see (RATCHET_BASELINES.md rule 1) and not patched locally.
_ENUMERATOR = re.compile(r"tracked_paths|ls-files|rglob\(|os\.walk\(|\.iterdir\(|\.glob\(")

#: Bound to files MATCHING `_ENUMERATOR`, never to guards found wanting. A `git ls-files`
#: returning nothing would otherwise pass this module having read zero files -- the exact
#: failure it exists to catch, inside itself.
#:
#: "MATCHED the enumerator" and "guards examined" are different quantities and this file's
#: comments used both for the same number (#17870). They differ by however many members match
#: incidentally -- three, enumerated in `_EXEMPT_NON_SCANNING`, and those three were exactly
#: the headroom the floor appeared to have before this change.
#:
#: MEASURED 2026-09-10 against `origin/main`: 201 tracked
#: `repo_tests/*_test.py`, of which 101 MATCHED `_ENUMERATOR` (80 before
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
#: RE-MEASURED 2026-10-04 (#17870, #17818), with the three non-scanning members below removed
#: from the population in the SAME change: 355 tracked `repo_tests/*_test.py` on this branch,
#: **172** MATCHED `_ENUMERATOR` after the exemptions (175 before them), and **140** matched it
#: without the glob alternative. Legal window: (140, 172].
#:
#: **NOT pinned at the top, and that breaks with the three prior re-pins -- say why, because
#: the two rules disagree.** #16147 AC1 chose the exact measured count, and 2026-09-11,
#: 2026-09-19 and 2026-09-29 each followed it: the top maximises the interval to the next
#: re-pin. #17870 AC2 is newer and more specific -- it says a population TIGHTENING must not
#: leave the assertion at exact equality, because at `len(guards) == MIN` the next legitimate
#: guard REMOVAL goes red. This change is that tightening, so the newer rule wins (CLAUDE.md,
#: "when rules conflict", precedence 2) and the pin sits two below full reach. The cost is a
#: slightly shorter interval to the next re-pin, which is the thing #16147 was buying; it is
#: named here rather than traded away silently.
#:
#: Do NOT "fix" the treadmill by deriving this from the tree. A floor computed
#: by the same enumerator it guards always agrees with itself and can never
#: fail; the hand-pinned number is the whole mechanism, and paying it forward on
#: each guard change is the cost of having a check that can fail.
#:
#: The window this must sit in is now asserted in one place rather than reconstructed from two
#: assertions in different tests -- see `_window_complaint` (#17818).
MIN_GUARDS_EXAMINED = 170

#: Members that MATCH `_ENUMERATOR` and scan nothing of the tree (#17870).
#:
#: `.glob(` matches any `.glob(` call, including one over a `tmp_path` fixture or the host
#: filesystem. Each of these was resolved by chasing its glob receiver's BINDING -- module
#: assignments, parameter defaults, call sites -- not by receiver name: `hook_self_sync_atomic`'s
#: receiver is the bare name `hooks`, indistinguishable from a genuine `HOOKS_DIR`, and an
#: earlier name-pattern classification returned "26 receiver unclear" for 26 cases of the
#: pattern simply not matching.
#:
#: Recorded as an exemption rather than by narrowing the regex, because a receiver-resolving
#: detector is a second instrument with its own blind spot, and the one being replaced has a
#: known, enumerated population. SHRINKS ONLY, mirrored in `_EXEMPT_BASELINE` so an addition
#: takes two edits a reviewer sees.
#:
#: Confirmed non-scanning and needing no `declare()`: the first two glob a `tmp_path` they
#: created. The third globs `/usr/lib/postgresql` -- the HOST -- which is a separate question
#: about whether a guard should do that at all, not a reach floor it is missing. That question
#: now has a home: #17937. It is filed rather than left here, because a host population has no
#: stable size -- on a runner without PostgreSQL the glob yields nothing and the guard passes
#: having examined nothing, which no reach floor over this tree can detect.
_EXEMPT_NON_SCANNING = frozenset(
    {
        "repo_tests/hook_self_sync_atomic_test.py",
        "repo_tests/prepush_hook_sync_17578_test.py",
        "repo_tests/sync_to_slm_db_update_classify_14459_test.py",
    }
)

#: `_EXEMPT_NON_SCANNING` as last recorded -- the same two-copy shape as `_GRANDFATHERED_BASELINE`.
_EXEMPT_BASELINE = frozenset(
    {
        "repo_tests/hook_self_sync_atomic_test.py",
        "repo_tests/prepush_hook_sync_17578_test.py",
        "repo_tests/sync_to_slm_db_update_classify_14459_test.py",
    }
)


def window_complaint(floor: int, narrowed: int, full: int) -> str:
    """The legal range for ``MIN_GUARDS_EXAMINED``, as one invariant (#17818).

    The constant does two jobs and only one of them is visible when it goes stale. It is the
    reach floor -- *the sweep found a real population* -- and it is the yardstick for whether
    that floor is tight enough to notice the `.glob(` term being dropped. Those two obligations
    are a WINDOW::

        narrowed < MIN_GUARDS_EXAMINED <= full

    Above ``full`` the floor fails on an honest tree; at or below ``narrowed`` the mutation test
    reads as clean while detecting nothing. Nobody wrote the window down, so a stale pin surfaced
    as ``assert 132 < 132`` on two innocent PRs and diagnosing it meant re-deriving both reach
    numbers by hand and reconstructing the rule from two assertions in different tests.

    Returns the complaint rather than asserting, so the negative controls can drive it with a
    deliberately wrong floor instead of mutating the module constant.
    """
    if narrowed < floor <= full:
        return ""
    return (
        f"MIN_GUARDS_EXAMINED is {floor}; it must be in ({narrowed}, {full}] -- re-pin to "
        f"{full}.\n"
        f"  > {narrowed}: below or at the reach WITHOUT `.glob(`, the mutation test cannot "
        f"notice that term being dropped and the sweep reads clean over a fifth fewer files.\n"
        f"  <= {full}: above the full reach, the floor fails on an honest tree.\n"
        f"Re-measure both numbers rather than nudging the pin: the window MOVES as the tree "
        f"grows, which is why this is the fourth re-pin and not the last."
    )


def _tracked_guards() -> list[Path]:
    """Enumerated through the canonical helper (#15926), not a direct git call.

    `tracked_paths` lets **git** do the pathspec matching, so the filter and the
    returned paths cannot disagree -- which is what #15510 cost when an
    exclusion was tested against the absolute path.
    """
    root = repo_root()
    return [root / rel for rel in tracked_paths(root, "repo_tests/*_test.py")]


def _examined_with(pattern: re.Pattern[str]) -> set[str]:
    """Guards a given enumerator pattern reaches. Used to mutate the detector."""
    root = repo_root()
    reached = set()
    for path in _tracked_guards():
        rel = path.relative_to(root).as_posix()
        if rel in _EXEMPT_NON_SCANNING:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if pattern.search(source):
            reached.add(rel)
    return reached


def reach_pair() -> tuple[int, int]:
    """``(narrowed, full)`` -- the two ends of the window, measured once."""
    without_glob = re.compile(_ENUMERATOR.pattern.replace(r"|\.glob\(", ""))
    return len(_examined_with(without_glob)), len(_examined_with(_ENUMERATOR))
