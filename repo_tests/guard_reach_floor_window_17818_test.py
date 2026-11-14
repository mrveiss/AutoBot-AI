# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`MIN_GUARDS_EXAMINED` must sit in a window, and a stale pin must say which one (#17818).

The constant does two jobs. It is the reach floor for `guard_reach_meta_test`'s sweep, and it
is the yardstick for whether that floor is tight enough to notice the glob alternative being
dropped from the enumerator -- the non-vacuity check on itself. Those two obligations are a
window, `narrowed < MIN_GUARDS_EXAMINED <= full`, and nobody had written it down.

**This docstring spells no enumerator token, and that is deliberate -- do not "improve" it
back.** `_ENUMERATOR` matches RAW SOURCE TEXT, comments and docstrings included, so a file that
merely QUOTES one of its alternatives joins the population it describes. The first version of
this file did exactly that: it named the glob term once, in prose, and became a fourth
non-scanning member of the very population #17870 removes three from -- in the change that
removes them. It would also have read as floored, because `assert complaint, "..."` is a bare
name and the detector accepts that. See #17941 for the class, and `_guard_reach_census`'s
`_ENUMERATOR` comment for where the limitation is recorded.

So when ten days of ordinary guard growth carried the narrowed reach up to the pin, two
unrelated PRs each added a guard, each became "the 132nd", and each went red on
`assert 132 < 132`. Neither was defective. Diagnosing it meant re-deriving both reach numbers
by hand and reconstructing the rule from two assertions in different test functions.

These cases drive `window_complaint` with deliberately wrong floors rather than mutating the
live constant, so each end of the window is exercised on purpose: a clean result from a
correctly pinned floor proves nothing about whether the rule can fire.

**Explicitly rejected, recorded so it is not re-proposed as an improvement: deriving the floor
from the tree.** A floor computed by the same enumerator it guards always agrees with itself
and can never fail. The hand-pinned number is the whole mechanism; the re-measurement is its
cost, not its defect.
"""

from __future__ import annotations

import pytest
from repo_tests._guard_reach_census import MIN_GUARDS_EXAMINED, reach_pair, window_complaint


def test_the_floor_sits_inside_its_window() -> None:
    """#17818: one invariant, one message, naming the legal range and the value to re-pin to.

    The treadmill is inherent -- the window moves as guards are added, so the pin has to be
    re-measured. What was wrong is that a stale pin failed as a puzzle: the old message said the
    floor "cannot detect the loss ... raise it", which says something is wrong and not what
    value is legal.
    """
    narrowed, full = reach_pair()
    assert not window_complaint(MIN_GUARDS_EXAMINED, narrowed, full)


@pytest.mark.parametrize("offset", [0, -1])
def test_a_floor_at_or_below_the_narrowed_reach_is_rejected(offset: int) -> None:
    """The `132 == 132` state, reproduced deliberately (#17818 AC2).

    Two unrelated PRs each became "the 132nd" guard and each went red on `assert 132 < 132`,
    neither defective. A check that cannot fail is the defect #15826 is about, so the floor's
    own guard gets the same treatment as every other.
    """
    narrowed, full = reach_pair()
    complaint = window_complaint(narrowed + offset, narrowed, full)
    assert complaint, f"a floor of {narrowed + offset} must be refused: at or below the narrowed reach"
    assert f"({narrowed}, {full}]" in complaint, "the message must name the legal range"
    assert f"re-pin to {full}" in complaint, "the message must name the value to re-pin to"


def test_a_floor_above_the_full_reach_is_rejected() -> None:
    """The other end: a floor the honest tree cannot clear."""
    narrowed, full = reach_pair()
    assert window_complaint(full + 1, narrowed, full), "a floor above the full reach must be refused"
    assert not window_complaint(full, narrowed, full), "the top of the window is legal -- the boundary is inclusive"
