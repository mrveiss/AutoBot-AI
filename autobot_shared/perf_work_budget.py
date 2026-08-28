# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Runner-calibrated budgets for benchmark assertions (#15055).

A benchmark that asserts a wall-clock millisecond count against a hardcoded
constant measures the runner, not the code. `system_benchmarks_performance_test`
carried 20 such assertions. One of them, `processor_startup_time < 500.0`, PASSED
on run 32837489748 and FAILED on 32839088246 (547.2ms) and 33154304714
(538.9ms) — the last of those on the commit immediately after a green one, whose
entire diff was a file that run deselects, with the benchmark module untouched on
that branch. Both overshoots sat within 10% of the budget: the signature of a
constant set near the runner's median rather than above its worst case. Those
selections run under `-n auto` on a shared, multi-tenant runner, so contention
from a noisy neighbour and from sibling workers is the normal condition, and a
constant at the median will keep meeting it.

WHAT REPLACES IT. One WORK UNIT is the wall-clock cost of `reference_workload()`
— a fixed, deterministic slice of pure-Python work — measured in THIS process, in
the same moment as the operation under test. Budgets are ratios against that
unit, so both sides of the comparison see the same contention: a runner that is
uniformly 3x slow inflates numerator and denominator alike and the ratio holds.

This is the move #14930 made for RSS (measure the delta the assertion always
meant, not the absolute figure the process happened to sit at) and the move
#13162 made for the cache and concurrency checks in that module (assert the
property, not the clock).

WHAT A UNIT BUDGET STILL CATCHES: an eager model load, a network call or a file
read added to a constructor, an O(n^2) traversal, a lock introduced on a hot
path. Those are order-of-magnitude changes, which is what a benchmark on a shared
runner can actually detect. A 10% wall-clock regression was never detectable
there — the noise band was already wider than that, which is exactly why the
constants fired on runner weather instead.

HOW TO CHANGE A BUDGET. Every site records its measurement on every run, pass or
fail, by two routes: a `[perf #15055] ...` line on stdout, which pytest shows for
a FAILING test (and locally under `-s`), and a `perf_work_units` property in the
junit XML, written for PASSING tests too and uploaded by marker-tests.yml as
`marker-suite-reports`. The junit route exists because those selections run under
`-n auto`, where xdist captures worker stdout and a green run would otherwise
report nothing — which is how the old constants went years without ever being
re-derived. Read the number off a run, then move the budget to sit above the
highest OBSERVED value with stated headroom. Never to a round figure chosen for
comfort, and never upwards because a run came close: a budget that has to be
relaxed to stay green is reporting a real change in the code's work, and that is
the finding, not the obstacle.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

REFERENCE_WORKLOAD_ITERATIONS = 20_000
REFERENCE_WORKLOAD_SAMPLES = 9

# The junit sink for reported measurements, set per test by
# `recording_work_units()` so call sites need not thread a fixture through.
_WORK_UNIT_RECORDER: ContextVar[Callable[[str, object], None] | None] = ContextVar(
    "autobot_work_unit_recorder", default=None
)


def reference_workload() -> int:
    """One work unit: a fixed, deterministic slice of pure-Python work.

    Deliberately CPU-bound, allocation-light and dependency-free, so its cost is
    a property of how contended the machine is right now and of nothing else.
    Never change its shape without re-deriving every budget measured against it —
    the unit is the yardstick, and silently rescaling it rescales all of them.
    """
    total = 0
    for i in range(REFERENCE_WORKLOAD_ITERATIONS):
        total += (i * i) % 7
    return total


def measure_reference_ms() -> float:
    """Cost in milliseconds of one work unit on this runner, right now.

    The MEDIAN of several samples, not the minimum: the denominator has to
    describe the contention the numerator was measured under. A best-of-N
    denominator would describe an idle machine while the numerator described a
    busy one, which is the failure the millisecond constants already had.
    """
    samples = []
    for _ in range(REFERENCE_WORKLOAD_SAMPLES):
        start = time.perf_counter()
        reference_workload()
        samples.append((time.perf_counter() - start) * 1000.0)
    samples.sort()
    return samples[len(samples) // 2]


@contextmanager
def recording_work_units(recorder: Callable[[str, object], None] | None) -> Iterator[None]:
    """Route measurements taken in this block to `recorder`, e.g. `record_property`."""
    token = _WORK_UNIT_RECORDER.set(recorder)
    try:
        yield
    finally:
        _WORK_UNIT_RECORDER.reset(token)


def assert_within_work_budget(elapsed_ms: float, budget_units: float, what: str) -> None:
    """Assert an operation cost fewer than `budget_units` calibrated work units.

    Fails on three distinct conditions, all of them real:

    * the operation exceeded its budget relative to this runner's own speed —
      the regression the benchmark exists to catch;
    * nothing was measured (`elapsed_ms` is zero, negative or not a number), so
      the assertion cannot pass vacuously by timing an operation that never ran
      or by being handed a stub in place of a measurement;
    * the calibration itself measured nothing, which would make the ratio
      meaningless rather than merely generous.
    """
    assert isinstance(elapsed_ms, (int, float)), f"{what}: no measurement was taken (got {elapsed_ms!r})"
    assert elapsed_ms > 0.0, f"{what}: measured {elapsed_ms}ms — the operation under test did not run"

    reference_ms = measure_reference_ms()
    assert reference_ms > 0.0, f"{what}: work-unit calibration measured {reference_ms}ms and cannot be a divisor"

    units = elapsed_ms / reference_ms
    report = (
        f"{what}: {units:.3f} work units (budget {budget_units}) " f"= {elapsed_ms:.3f}ms / {reference_ms:.3f}ms unit"
    )
    print(f"[perf #15055] {report}")  # noqa: print
    recorder = _WORK_UNIT_RECORDER.get()
    if recorder is not None:
        recorder("perf_work_units", report)

    assert units < budget_units, (
        f"{report}. This is a load-invariant ratio, not a wall-clock ceiling — "
        f"investigate the code, do not raise it."
    )
