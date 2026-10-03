# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The relative reach floor fires on a collapsed sweep and not on a growing tree (#17142).

`hooks-path-override` was re-pinned seventeen times and `conflict-marker-scanned-files` reached one
file of headroom on the same afternoon. Both carried `floor=N, growth=M`, and every one of those
numbers was correct when written -- a constant does not rot, the tree grows past it. So the
allowance was the defect rather than either constant, and the owner's ruling was to make the floor
relative rather than to raise it an eighteenth time.

**Why the reference is external, which the first design got wrong.** A reach floor asks whether the
sweep found the tree. If the sweep breaks, every number derived from it breaks together -- so
comparing two of its own outputs compares a number to itself. The first design for this change
proposed `examined()` against `population()`, and those are the same call: `examined` is
`population` plus the floor check. It would have passed unconditionally. The denominator has to be
an enumeration no guard owns, which is `git ls-files`.

These cases drive `Reach` with synthetic declarations rather than the live tree, so each direction
is exercised deliberately: a clean result on a clean tree proves nothing about whether the check
can fire.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._reach import Reach, ReachFloorError, declare, floor_div_fraction

_ROOT = Path("/nonexistent-root-never-read")


def _reach(found: int, *, fraction: float, reference: int, skips: int = 0) -> Reach:
    """A declaration whose sweep and reference are both fixed, so only the rule is under test."""
    return Reach(
        name=f"synthetic-{found}-of-{reference}",
        discover=lambda _root: list(range(found)),
        floor=0,
        what="synthetic items",
        skips=skips,
        min_fraction=fraction,
        reference=lambda _root: reference,
    )


def test_rounding_is_down_so_a_fraction_of_one_means_every_file() -> None:
    """`1.0` has to be satisfiable by a sweep that reached the whole reference.

    Rounding up would make `min_fraction=1.0` unsatisfiable, and that is the value
    `conflict-marker-scanned-files` declares -- it scans every tracked file.
    """
    assert floor_div_fraction(10999, 1.0) == 10999
    assert floor_div_fraction(10999, 0.615) == 6764
    assert floor_div_fraction(3, 0.5) == 1


def test_a_sweep_covering_its_declared_share_passes() -> None:
    """Positive control: without it, a rule that always raises would pass every case below."""
    assert len(_reach(6764, fraction=0.615, reference=10999).examined(_ROOT)) == 6764


def test_a_sweep_exactly_on_the_fraction_passes() -> None:
    """The boundary is inclusive: a declared fraction is a floor, not a threshold to exceed."""
    assert len(_reach(10999, fraction=1.0, reference=10999).examined(_ROOT)) == 10999


@pytest.mark.parametrize(
    "found,fraction,reference",
    [
        (0, 0.615, 10999),  # total collapse
        (300, 0.615, 10999),  # the shape a broken glob produces
        (6763, 0.615, 10999),  # one file below the declared share
        (10998, 1.0, 10999),  # one file short of a whole-tree scan
    ],
)
def test_a_collapsed_sweep_is_refused(found: int, fraction: float, reference: int) -> None:
    with pytest.raises(ReachFloorError) as excinfo:
        _reach(found, fraction=fraction, reference=reference).examined(_ROOT)
    assert "below the declared min_fraction" in str(excinfo.value)


@pytest.mark.parametrize("scale", [1, 2, 10, 100])
def test_tree_growth_does_not_consume_the_margin(scale: int) -> None:
    """The property the absolute floor did not have, and the whole point of the change.

    A sweep holding its share passes at every tree size. The same sweep under `floor=6736` fails
    nothing as the tree grows -- it is the FLOOR that goes stale, requiring a re-pin -- so this
    asserts the thing seventeen re-pins were paying for.
    """
    found, reference = 7136 * scale, 10999 * scale
    assert len(_reach(found, fraction=0.615, reference=reference).examined(_ROOT)) == found


def test_a_reference_of_zero_raises_rather_than_passing() -> None:
    """`count >= 0 * fraction` is true of every sweep, including a broken one.

    `reach_declarations_test` hands every declaration an empty repository to prove its floor can
    fire. A fraction treating an empty reference as satisfied would be the one declaration in the
    registry whose floor cannot fire -- and on its own terms, a reference that found nothing is a
    failed measurement, not a clean result.
    """
    with pytest.raises(ReachFloorError) as excinfo:
        _reach(0, fraction=0.615, reference=0).examined(_ROOT)
    assert "reference enumeration found 0 files" in str(excinfo.value)


def test_declare_refuses_a_declaration_bounded_by_nothing() -> None:
    with pytest.raises(ValueError, match="positive floor or a min_fraction"):
        declare(name="unbounded-synthetic", discover=lambda _r: [], what="nothing", floor=0)


@pytest.mark.parametrize("bad", [0, -0.1, 1.5, 2])
def test_declare_refuses_a_fraction_outside_the_unit_interval(bad: float) -> None:
    with pytest.raises(ValueError, match="min_fraction must be in"):
        declare(name=f"bad-fraction-{bad}", discover=lambda _r: [], what="nothing", min_fraction=bad)


def test_declare_refuses_both_bounds_at_once() -> None:
    """A declaration carrying both is read as whichever one the reader looked at."""
    with pytest.raises(ValueError, match="min_fraction replaces floor/growth"):
        declare(
            name="both-bounds-synthetic",
            discover=lambda _r: [],
            what="nothing",
            floor=100,
            min_fraction=0.5,
        )


#: The floors the two adopted guards carried before this change, and the tracked-file count they
#: were measured against. Recorded so the migration's central claim -- that the fraction is
#: TIGHTER than the constant it replaced -- is asserted rather than stated in a commit message.
#:
#: Safe as a permanent assertion rather than a snapshot: the implied floor RISES with the tree, so
#: `implied > old` cannot become false through growth. It would only fail if someone lowered a
#: fraction below what the old constant demanded, which is exactly the regression to catch.
_SUPERSEDED = {
    # (superseded floor, the count of the guard's OWN reference when it was measured)
    #
    # The second number must be the denominator that declaration's `reference` returns, not the
    # tracked-tree total. `hooks-path-override` references its suffix-matched population (7106 on
    # 24a9a1d46f), where an earlier version of this change wrongly took a fraction of all 11000
    # tracked files -- arithmetically tighter today and not scale-free, because the floor would
    # then rise with the tree while the counted subset grew at its own rate. Recording the wrong
    # denominator here would have made this test certify that mistake.
    "hooks-path-override": (6736, 7106),
    "conflict-marker-scanned-files": (10000, 10999),
}


@pytest.mark.parametrize("name", sorted(_SUPERSEDED))
def test_each_adopted_fraction_is_tighter_than_the_floor_it_replaced(name: str) -> None:
    import repo_tests.hooks_path_override_15961_test  # noqa: F401, PLC0415
    import repo_tests.no_conflict_markers_in_tracked_files_17297_test  # noqa: F401, PLC0415
    from repo_tests._reach import REGISTRY

    reach = REGISTRY[name]
    old_floor, tracked_then = _SUPERSEDED[name]
    assert reach.min_fraction is not None, f"{name} no longer declares a fraction"
    implied = floor_div_fraction(tracked_then, reach.min_fraction)
    assert implied > old_floor, (
        f"{name}: min_fraction={reach.min_fraction} implies a floor of {implied} against the "
        f"{tracked_then} tracked files it was measured on, which is NOT tighter than the "
        f"{old_floor} it replaced. The change would weaken the guard."
    )


# --- the completion bound, which the first version of this mode silently removed -------------
#
# `completed()` is the stronger of the two bounds: `examined` says what was listed, `completed`
# says what was opened, and a sweep can list everything and read almost nothing. The first version
# left `completed()` on `_require`, which compares against `floor` — and a relative declaration
# carries `floor=0`, so it passed for any count including zero (CodeRabbit, #17915).


def test_a_relative_declaration_refuses_a_collapsed_completion() -> None:
    """Listing the tree and finishing none of it is the case `completed()` exists for."""
    reach = _reach(7137, fraction=0.98, reference=7106)
    with pytest.raises(ReachFloorError) as excinfo:
        reach.completed(0, _ROOT)
    assert "completed 0" in str(excinfo.value)


def test_a_relative_declaration_accepts_a_completion_holding_its_share() -> None:
    """Positive control: the bound must be satisfiable by a sweep that did the work."""
    _reach(7137, fraction=0.98, reference=7106).completed(7136, _ROOT)


def test_completed_without_a_root_is_refused_on_a_relative_declaration() -> None:
    """Refused rather than silently falling back to the absolute path.

    A default would reintroduce the exact silence this fixes: `floor=0` makes `_require` pass for
    every count, so a call site that forgot the root would assert nothing and look identical to one
    that did not.
    """
    with pytest.raises(ReachFloorError, match="completed\\(\\) needs the root"):
        _reach(7137, fraction=0.98, reference=7106).completed(0)


def test_an_absolute_declaration_still_completes_without_a_root() -> None:
    """The 25 call sites on absolute declarations are untouched by the new parameter."""
    absolute = Reach(name="synthetic-absolute", discover=lambda _r: list(range(10)), floor=5, what="items")
    absolute.completed(7)
    with pytest.raises(ReachFloorError):
        absolute.completed(3)
