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
    assert_within_work_budget,
    measure_reference_ms,
    recording_work_units,
    reference_workload,
)


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
