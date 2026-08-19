# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deriving what a process step costs to run (#14598, #14607).

Cost is computed, never stored:

    minutes / 60 * hourly_rate            -> cost per run
    cost per run * runs_per_month         -> cost per month
    cost per month * 12                   -> cost per year

A stored cost would go stale the moment a rate changed, and nothing about the
number would say so. Deriving it means a rate change is reflected everywhere at
once, and there is no second producer to disagree with.

The central rule here is that **missing is not zero**. A step with no recorded
time, or a role with no rate, is *not costable* — distinct from costing
nothing. Returning 0.0 for it would quietly understate a total, and the reader
has no way to tell an unmeasured step from a free one. Every caller therefore
gets ``None`` plus a reason, and any rollup reports coverage alongside its
total (#14599).

This module owns the arithmetic only. It performs no authorisation and no I/O:
the callers already assert company access, and keeping the rule pure is what
lets it be tested without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

#: Minutes in an hour. Named because a bare 60 in a money calculation reads as
#: a magic number, and a wrong one is invisible.
MINUTES_PER_HOUR = Decimal(60)

#: Months in a year, for the annualised figure.
MONTHS_PER_YEAR = Decimal(12)


class NotCostable(str, Enum):
    """Why a step could not be costed. Never conflated with a zero cost."""

    NO_TIME = "no_estimated_minutes"
    NO_FREQUENCY = "no_runs_per_month"
    NO_RATE = "no_role_rate"


@dataclass(frozen=True)
class StepCost:
    """The derived cost of one step, or the reason there is none.

    ``per_run`` is available as soon as time and a rate exist; ``per_month`` and
    ``per_year`` additionally need a frequency. They are reported separately
    rather than collapsed into one nullable number, because "we know what one
    run costs but not how often it runs" is a real and common state, and
    flattening it would throw away the half that is known.
    """

    per_run: Optional[Decimal]
    per_month: Optional[Decimal]
    per_year: Optional[Decimal]
    currency: Optional[str]
    #: Empty when fully costable. Order is stable so callers can compare.
    missing: tuple[NotCostable, ...]

    @property
    def is_costable(self) -> bool:
        """True only when a per-run figure exists — never merely 'no error'."""
        return self.per_run is not None


def derive_step_cost(
    estimated_minutes: Optional[int],
    runs_per_month: Optional[int],
    hourly_rate: Optional[Decimal],
    currency: Optional[str],
) -> StepCost:
    """Cost one step from its inputs, reporting what is missing rather than guessing.

    ``0`` is a legitimate recorded value and is treated as such: a step that
    genuinely takes no time, or runs zero times a month, costs zero — that is a
    measurement. ``None`` means nobody measured it, which is not.
    """
    missing: list[NotCostable] = []
    if estimated_minutes is None:
        missing.append(NotCostable.NO_TIME)
    if runs_per_month is None:
        missing.append(NotCostable.NO_FREQUENCY)
    if hourly_rate is None:
        missing.append(NotCostable.NO_RATE)

    per_run: Optional[Decimal] = None
    if estimated_minutes is not None and hourly_rate is not None:
        # Multiply before dividing: minutes x rate is exact, and there is then
        # a single rounding rather than one per operand.
        per_run = (Decimal(estimated_minutes) * Decimal(hourly_rate)) / MINUTES_PER_HOUR

    per_month: Optional[Decimal] = None
    per_year: Optional[Decimal] = None
    if estimated_minutes is not None and hourly_rate is not None and runs_per_month is not None:
        # Derived from the raw inputs rather than from `per_run`, so the
        # division rounds once instead of being multiplied up. 20 minutes a run
        # at 0.10/hour, 3 runs a month, is exactly 0.10 a month; computing it
        # as `per_run * runs` yields 0.0999... because the third-of-an-hour was
        # rounded first and the error was then tripled. These figures are
        # summed into totals people are asked to trust, so the compounding
        # matters more than the single value does.
        per_month = (Decimal(estimated_minutes) * Decimal(runs_per_month) * Decimal(hourly_rate)) / MINUTES_PER_HOUR
        per_year = per_month * MONTHS_PER_YEAR

    return StepCost(
        per_run=per_run,
        per_month=per_month,
        per_year=per_year,
        # The unit travels with the number. A bare amount reads as whatever the
        # reader assumes, and there is more than one currency in the world even
        # though the researched product supports one.
        currency=currency if per_run is not None else None,
        missing=tuple(missing),
    )
