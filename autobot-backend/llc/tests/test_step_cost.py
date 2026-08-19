# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deriving step cost, and refusing to invent one (GH#14598, GH#14607).

The rule these protect is that **missing is not zero**. Returning 0.0 for a
step nobody measured understates every total it feeds, and the reader cannot
tell an unmeasured step from a free one. That failure shape has already shipped
three times in this area under a different disguise — an empty surface reading
as "nothing" rather than "not known" (#14064, #13617, #14556).
"""

from __future__ import annotations

from decimal import Decimal

from llc.services.step_cost import NotCostable, derive_step_cost


def test_cost_is_derived_from_time_frequency_and_rate() -> None:
    """30 minutes at 120/hour = 60 per run; 10 runs a month = 600; 7200 a year."""
    cost = derive_step_cost(estimated_minutes=30, runs_per_month=10, hourly_rate=Decimal("120"), currency="EUR")

    assert cost.per_run == Decimal("60")
    assert cost.per_month == Decimal("600")
    assert cost.per_year == Decimal("7200")
    assert cost.currency == "EUR"
    assert cost.missing == ()
    assert cost.is_costable is True


def test_an_unmeasured_step_is_not_costable_rather_than_free() -> None:
    """No recorded time yields None and a reason — never 0."""
    cost = derive_step_cost(estimated_minutes=None, runs_per_month=10, hourly_rate=Decimal("120"), currency="EUR")

    assert cost.per_run is None
    assert cost.is_costable is False
    assert NotCostable.NO_TIME in cost.missing
    # The distinction that matters: this must not be mistaken for a zero cost.
    assert cost.per_run != Decimal(0)


def test_a_role_with_no_rate_makes_its_steps_not_costable() -> None:
    cost = derive_step_cost(estimated_minutes=30, runs_per_month=10, hourly_rate=None, currency=None)

    assert cost.per_run is None
    assert NotCostable.NO_RATE in cost.missing


def test_zero_is_a_measurement_and_costs_zero() -> None:
    """A recorded 0 is not the same as an absent value.

    Conflating them is how the guard fails open: if the implementation tested
    falsiness instead of ``is None``, a genuine zero would be reported as
    'not measured' and quietly dropped from coverage.
    """
    cost = derive_step_cost(estimated_minutes=0, runs_per_month=0, hourly_rate=Decimal("120"), currency="USD")

    assert cost.per_run == Decimal(0)
    assert cost.per_month == Decimal(0)
    assert cost.is_costable is True
    assert cost.missing == ()


def test_known_per_run_survives_an_unknown_frequency() -> None:
    """Half-known is reported as half-known, not discarded.

    "We know what one run costs but not how often it runs" is a real state, and
    collapsing it to a single nullable number would throw away the half that is
    known.
    """
    cost = derive_step_cost(estimated_minutes=30, runs_per_month=None, hourly_rate=Decimal("120"), currency="GBP")

    assert cost.per_run == Decimal("60")
    assert cost.per_month is None
    assert cost.per_year is None
    assert cost.missing == (NotCostable.NO_FREQUENCY,)


def test_currency_travels_with_the_number() -> None:
    """An amount with no unit reads as whatever the reader assumes."""
    costed = derive_step_cost(60, 1, Decimal("50"), "PLN")
    assert (costed.per_run, costed.currency) == (Decimal("50"), "PLN")

    # And no currency is claimed when there is no amount to attach it to.
    uncosted = derive_step_cost(None, 1, Decimal("50"), "PLN")
    assert uncosted.currency is None


def test_money_is_exact_not_floating_point() -> None:
    """A third of an hour at a real rate must not drift.

    20 minutes at 0.1/hour is exactly 0.0333... in decimal terms; the point is
    that the arithmetic stays in Decimal rather than becoming a float, because
    these figures are summed into totals people are asked to trust.
    """
    cost = derive_step_cost(20, 3, Decimal("0.1"), "USD")

    assert isinstance(cost.per_run, Decimal)
    assert isinstance(cost.per_month, Decimal)
    # 20/60 * 0.1 * 3 == 0.1 exactly, which binary floating point cannot promise.
    assert cost.per_month == Decimal("0.1")
