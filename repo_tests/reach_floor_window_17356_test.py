# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A floor pinned at the bottom of its window is refused by the primitive (#17356).

`population - (growth + skips)` is the arithmetic every re-pin reaches for, and it has **zero
tolerance by construction**: correct at the instant of measurement, red for every tree with one
more file. Seven reds, five declarations, one night -- and the last two were created by the
author who had just written up why that formula does not work, within the hour, twice, noticing
neither time until the suite failed.

The standing objection to a convention is that people who understand the rule will follow it.
That is retired by a case where the person who had written the rule down did not. So the rule
moves into the tool: `_reach.verify_floor` refuses a floor in the bottom tenth of `growth` and
names the mid-window value, so the fix is mechanical rather than a second judgement call.

Both bounds, not one. The gap bound is `population - (skips + growth)`; the other is
`population - skips`, the most `completed()` can clear, and every re-pin comment in
`hooks_path_override_15961_test.py` quotes only the first. That is why there are seventeen.

Synthetic declarations throughout: a floor that happens to be correct on today's tree proves
nothing about whether the refusal can fire.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._reach import Reach, ReachFloorError

_ROOT = Path("/nonexistent-root-never-read")


def _reach(*, floor: int, population: int, growth: int, skips: int = 0) -> Reach:
    return Reach(
        name=f"synthetic-{floor}-of-{population}-g{growth}-s{skips}",
        discover=lambda _root: list(range(population)),
        floor=floor,
        what="synthetic items",
        growth=growth,
        skips=skips,
    )


def test_the_bottom_of_the_window_is_refused() -> None:
    """`floor = population - growth` exactly: the shape that produced every re-pin."""
    with pytest.raises(ReachFloorError) as caught:
        _reach(floor=600, population=1000, growth=400).verify_floor(_ROOT)
    assert "bottom" in str(caught.value)


def test_the_refusal_names_the_mid_window_value() -> None:
    """Mechanical, not a second judgement call: the message carries the number to write down."""
    with pytest.raises(ReachFloorError) as caught:
        _reach(floor=600, population=1000, growth=400).verify_floor(_ROOT)
    assert "Pin MID-window, at 800." in str(caught.value)


def test_the_refusal_states_both_bounds_not_just_the_gap_bound() -> None:
    """`completed()` is the upper bound, and quoting only the lower one is why there were seventeen.

    With `skips=300` a sweep finishes `population - skips` items, so a floor above 700 fails
    `completed()` while satisfying `verify_floor`. The window is [300, 700], not [300, 1000].
    """
    with pytest.raises(ReachFloorError) as caught:
        _reach(floor=300, population=1000, growth=400, skips=300).verify_floor(_ROOT)
    message = str(caught.value)
    assert "[300, 700]" in message, "the window must state both ends"
    assert "completed() can clear" in message, "the upper bound must say what makes it the upper bound"
    assert "Pin MID-window, at 500." in message


def test_a_mid_window_floor_passes() -> None:
    """The positive control: a rule that refuses everything is not a rule."""
    _reach(floor=800, population=1000, growth=400).verify_floor(_ROOT)


@pytest.mark.parametrize("floor", [640, 800, 1000])
def test_a_floor_clear_of_the_bottom_passes(floor: int) -> None:
    """Only the BOTTOM of the window is refused -- everything above it stays legal.

    640 is the first legal value with `growth=400`: a tenth of the band left unspent. 800 is
    mid-window, the value the refusal recommends. 1000 is equality, which `growth`'s own
    docstring calls the right default when ordinary work does not move the number.
    """
    _reach(floor=floor, population=1000, growth=400).verify_floor(_ROOT)


def test_one_file_below_the_margin_is_refused() -> None:
    """The boundary is checked from both sides, or "it fires" is a claim about one number."""
    with pytest.raises(ReachFloorError):
        _reach(floor=639, population=1000, growth=400).verify_floor(_ROOT)


def test_an_equality_pin_with_no_growth_is_exempt() -> None:
    """`growth=0` has no window to sit in the bottom of.

    A declaration whose population ordinary work does not move declares `growth=0` deliberately
    -- a fixed set of workflows, of provider baselines, of scrub sites. Applying a margin to a
    zero-width band would refuse the one shape `growth`'s docstring asks for.
    """
    _reach(floor=1000, population=1000, growth=0).verify_floor(_ROOT)


def test_a_small_band_keeps_a_one_item_margin() -> None:
    """A tenth of 3 rounds to 1 rather than to 0, so the bottom is still refused at small sizes."""
    with pytest.raises(ReachFloorError):
        _reach(floor=3, population=6, growth=3).verify_floor(_ROOT)
    _reach(floor=4, population=6, growth=3).verify_floor(_ROOT)


def test_a_floor_above_the_population_still_reports_that_first() -> None:
    """The pre-existing refusals are untouched: an impossible floor is not a window complaint."""
    with pytest.raises(ReachFloorError, match="exceeds the live population"):
        _reach(floor=1200, population=1000, growth=400).verify_floor(_ROOT)


def test_a_floor_below_the_window_still_reports_the_allowance_breach() -> None:
    with pytest.raises(ReachFloorError, match="exceeds the declared allowance"):
        _reach(floor=100, population=1000, growth=400).verify_floor(_ROOT)


def test_window_reports_both_bounds_and_the_value_to_pin() -> None:
    assert _reach(floor=800, population=1000, growth=400, skips=100).window(_ROOT) == (500, 900, 700)
