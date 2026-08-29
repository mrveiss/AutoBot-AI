# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guards on the work-budget harness itself (#15055).

A budget that can pass without measuring anything is the failure mode the
millisecond constants were replaced to avoid repeating, so the property is
asserted here rather than left to review. Deliberately unmarked: these are
fast and deterministic, so they belong in the normal gate rather than in the
marker-excluded selection whose benchmarks they underwrite.
"""

import pytest

from autobot_shared.perf_work_budget import (
    MeasurementStarved,
    assert_within_work_budget,
    measure_reference_ms,
    measure_with_starvation_retry,
    recording_work_units,
    reference_workload,
)

# Only the classes below hold coroutine tests; the ones above are plain sync
# functions and this marker is a no-op for them (#15266).
pytestmark = pytest.mark.asyncio


class TestWorkBudgetHarness:
    """The assertion must be neither vacuously green nor unconditionally green."""

    def test_zero_elapsed_cannot_pass(self):
        """A measurement of zero is a measurement that did not happen."""
        with pytest.raises(AssertionError, match="did not run"):
            assert_within_work_budget(0.0, 1000.0, "zero measurement")

    def test_negative_elapsed_cannot_pass(self):
        """A negative duration means the clock, not the code, was measured."""
        with pytest.raises(AssertionError, match="did not run"):
            assert_within_work_budget(-1.0, 1000.0, "negative measurement")

    def test_absent_measurement_cannot_pass(self):
        """A missing measurement fails instead of comparing None to a budget."""
        with pytest.raises(AssertionError, match="no measurement was taken"):
            assert_within_work_budget(None, 1000.0, "absent measurement")

    def test_budget_still_fails_when_exceeded(self):
        """The counterpart guard: the assertion is not unconditionally green."""
        with pytest.raises(AssertionError, match="work units"):
            assert_within_work_budget(measure_reference_ms() * 100.0, 1.0, "deliberate overrun")

    def test_work_unit_is_measurable_and_positive(self):
        """The divisor is a real measurement, so a ratio means something."""
        reference_ms = measure_reference_ms()
        assert reference_ms > 0.0, f"work-unit calibration measured {reference_ms}ms"

    def test_reference_workload_is_deterministic(self):
        """The yardstick does the same work every time it is used."""
        assert reference_workload() == reference_workload()

    def test_measurements_reach_the_recorder(self):
        """Every site reports, so budgets can be re-derived from a GREEN run."""
        recorded: list[tuple[str, object]] = []
        with recording_work_units(lambda name, value: recorded.append((name, value))):
            assert_within_work_budget(measure_reference_ms(), 1000.0, "recorded measurement")

        assert [name for name, _ in recorded] == ["perf_work_units"], f"nothing was reported: {recorded}"
        assert "recorded measurement" in str(recorded[0][1])

    def test_recorder_is_cleared_after_the_block(self):
        """A recorder from one test never leaks into the next."""
        with recording_work_units(lambda name, value: None):
            pass
        # No recorder installed: the assertion still works and reports nowhere.
        assert_within_work_budget(measure_reference_ms(), 1000.0, "unrecorded measurement")


class TestStarvationRetry:
    """``measure_with_starvation_retry``: a starved window retries, a real
    measured failure never does (#15266). The retry exists so a window too
    short to hold a median is neither a false pass (silently skipped) nor a
    false regression (failed on ordinary runner load) — see
    ``process_offload_test.py::test_a_scan_in_a_process_does_not_delay_the_event_loop``
    for the call site this was built for.
    """

    async def test_succeeds_without_retry_when_the_first_attempt_is_not_starved(self):
        calls = 0

        async def measure():
            nonlocal calls
            calls += 1
            return "measured"

        result = await measure_with_starvation_retry(measure, max_attempts=3, what="unstarved")
        assert result == "measured"
        assert calls == 1, "a clean first attempt must not be retried"

    async def test_retries_a_starved_window_and_succeeds_once_it_is_not(self):
        calls = 0

        async def measure():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise MeasurementStarved(f"attempt {calls} starved")
            return "measured on the third attempt"

        result = await measure_with_starvation_retry(measure, max_attempts=3, what="eventually unstarved")
        assert result == "measured on the third attempt"
        assert calls == 3

    async def test_persistent_starvation_fails_after_the_bounded_ceiling(self):
        """Starvation on every attempt still goes red — this is not a skip."""
        calls = 0

        async def measure():
            nonlocal calls
            calls += 1
            raise MeasurementStarved(f"attempt {calls} starved")

        with pytest.raises(AssertionError, match="starved on all 3 attempts"):
            await measure_with_starvation_retry(measure, max_attempts=3, what="persistently starved")
        assert calls == 3, "the ceiling is bounded, not unbounded"

    async def test_a_measured_regression_is_never_retried_or_masked(self):
        """The mutation argument (#15266): a real regression fails on attempt one.

        ``MeasurementStarved`` is the ONLY exception this retries. A plain
        ``AssertionError`` — what a completed measurement raises when its own
        ratio budget fails, e.g. the ~1.994x reading a forced in-process scan
        produces against the 1.5 budget — propagates immediately. It can never
        land on a lucky retry and can never be averaged away by one.
        """
        calls = 0

        async def measure():
            nonlocal calls
            calls += 1
            raise AssertionError("1.994x its own idle baseline (budget 1.5)")

        with pytest.raises(AssertionError, match="1.994x"):
            await measure_with_starvation_retry(measure, max_attempts=3, what="regressed")
        assert calls == 1, "a measured regression must not be retried"
