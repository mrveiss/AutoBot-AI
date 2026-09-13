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
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TypeVar

REFERENCE_WORKLOAD_ITERATIONS = 20_000
REFERENCE_WORKLOAD_SAMPLES = 9

_T = TypeVar("_T")

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


def assert_within_work_budget(
    elapsed_ms: float, budget_units: float, what: str, calibrated_under: str | None = None
) -> None:
    """Assert an operation cost fewer than `budget_units` calibrated work units.

    Fails on three distinct conditions, all of them real:

    * the operation exceeded its budget relative to this runner's own speed —
      the regression the benchmark exists to catch;
    * nothing was measured (`elapsed_ms` is zero, negative or not a number), so
      the assertion cannot pass vacuously by timing an operation that never ran
      or by being handed a stub in place of a measurement;
    * the calibration itself measured nothing, which would make the ratio
      meaningless rather than merely generous.

    `calibrated_under` names the STATE the budget was measured in, and is
    reported on breach (#15342). A budget is only meaningful together with that
    state: `Multimodal processor startup` was calibrated at 315.602 units while
    `VisionProcessor`'s CLIP load was raising `TypeError` (#15054), so the
    constructor exited early. When #15297 fixed that load, the same constructor
    began doing the work it had been skipping and measured ~1500 units. Nothing
    regressed; the baseline's premise had gone.

    Without the state recorded, that breach is indistinguishable from a real
    slowdown, and the failure text — "investigate the code, do not raise it" —
    sends the reader hunting a regression that does not exist. With it, the two
    cases read differently, which is the whole point.
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

    if calibrated_under:
        state_note = (
            f"\n  budget calibrated under: {calibrated_under}"
            f"\n  If that state no longer holds this is a RE-BASELINE, not a regression:"
            f"\n  confirm which, then reset the budget and update `calibrated_under`."
        )
    else:
        state_note = (
            "\n  This is a load-invariant ratio, not a wall-clock ceiling — " "investigate the code, do not raise it."
        )

    assert units < budget_units, f"{report}.{state_note}"


def assert_within_baseline_ratio(
    measured_ms: float,
    baseline_ms: float,
    budget_ratio: float,
    what: str,
) -> None:
    """Assert a measurement stayed within `budget_ratio` of its OWN idle baseline.

    The sibling of `assert_within_work_budget`, for quantities a CPU work unit
    cannot normalise (#15221).

    WHY THE WORK UNIT DOES NOT TRANSFER TO A CONTENTION MEASURE. `reference_workload()`
    is a CPU-throughput yardstick. It normalises a numerator that is also CPU
    throughput. It does not normalise event-loop wakeup latency, for two
    independent reasons:

    * Timed WHILE the operation under test runs, the yardstick is starved by
      exactly the contention the assertion exists to detect, so numerator and
      denominator inflate together and the signal cancels. A test that cannot
      fail is not a test.
    * Timed BEFORE or AFTER instead, it describes a different moment and a
      different physical quantity. Measured on the #15221 host it spread
      1.43ms-3.27ms across six consecutive samples — a 2.3x swing in the
      DENOMINATOR alone, wider than the 2.0x signal the assertion has to
      resolve. It would manufacture flake rather than absorb it.

    WHAT REPLACES IT. The baseline is the SAME quantity as the numerator, taken
    on the same loop in the same process in an adjacent window, differing only in
    whether the operation under test was in flight. Under an external delay L the
    baseline reads `b + L` and the measurement `b + L + tax`, so the ratio is
    `1 + tax/(b + L)` — decreasing in L. Load pushes it toward 1.0 and away from
    the budget, and the regression it guards raises only the numerator.

    THE PREMISE THAT ALGEBRA RESTS ON, stated because it is not guaranteed: L
    must be COMPARABLE across the baseline and measurement windows. They are
    temporally disjoint — a caller typically spans a second or two end to end —
    so a load burst from a sibling job that lands inside the measurement window
    and is gone before the baseline is resampled inflates the numerator with no
    matching rise in the denominator, and pushes the ratio UP. That is a real
    false-failure path this helper does not exclude. It is much narrower than the
    absolute wall-clock ceiling it replaces, which tripped on any load bump at
    all: a spike now has to be timed to miss the baseline windows entirely. But
    the guarantee is "much less likely", NOT "impossible", and a red here is not
    on its own proof of a regression. Callers should bracket the measurement with
    a baseline window either side rather than take one before it, so that a
    monotone drift in load is shared by both terms.

    TWO MORE THINGS A CALLER OWNS, not this helper:

    * A SETTLING GAP between the operation and a trailing baseline window. If the
      operation's effects outlive its completion — pool teardown, a GC pause,
      page-cache pressure — that tax lands in the "idle" baseline, inflating the
      denominator and SHRINKING the ratio. That weakens detection exactly where
      it matters, and it fails quietly. #15221's caller samples with no gap
      because its workload demonstrably leaves nothing behind; a caller whose
      does should wait it out first.
    * The STATISTIC over each window. A median answers "did the typical sample
      move", so a regression that delays only a minority of samples will not move
      it. Choose a high percentile instead where a tail is the thing at stake.

    Fails on four distinct conditions, all of them real: the measurement exceeded
    its budget relative to its own baseline; nothing was measured; no baseline
    was measured; or the baseline is zero and cannot be a divisor.
    """
    assert isinstance(measured_ms, (int, float)), f"{what}: no measurement was taken (got {measured_ms!r})"
    assert isinstance(baseline_ms, (int, float)), f"{what}: no baseline was taken (got {baseline_ms!r})"
    assert measured_ms > 0.0, f"{what}: measured {measured_ms}ms — the operation under test did not run"
    assert baseline_ms > 0.0, f"{what}: baseline measured {baseline_ms}ms and cannot be a divisor"

    ratio = measured_ms / baseline_ms
    report = (
        f"{what}: {ratio:.3f}x its own idle baseline (budget {budget_ratio}) "
        f"= {measured_ms:.3f}ms / {baseline_ms:.3f}ms idle"
    )
    print(f"[perf #15221] {report}")  # noqa: print
    recorder = _WORK_UNIT_RECORDER.get()
    if recorder is not None:
        recorder("perf_baseline_ratio", report)

    assert ratio < budget_ratio, (
        f"{report}. This is a ratio against a baseline measured on the same loop "
        f"moments earlier, not a wall-clock ceiling — runner load moves both "
        f"terms, so investigate the code, do not raise it."
    )


class MeasurementStarved(Exception):
    """A measurement window could not collect enough samples to mean anything.

    Raised by a caller's measurement callable, never by this module — the
    caller is the one that knows how many samples its window needs. Deliberately
    NOT an `AssertionError`: `measure_with_starvation_retry` catches only this
    type, so a real assertion failure inside the callable (a regression the
    measurement *did* complete and then failed) is never mistaken for a window
    that produced no measurement at all, and is never retried or swallowed.
    """


async def measure_with_starvation_retry(
    measure: Callable[[], Awaitable[_T]],
    *,
    max_attempts: int,
    what: str,
) -> _T:
    """Retry `measure` a small bounded number of times if its window starves (#15266).

    A window that could not collect enough samples is neither a pass nor a
    failure — it is a runner that was too busy to take the measurement at all,
    which says nothing about the code under test. Failing outright on that
    reports an environment condition as a code regression (#15221's second
    sighting); silently skipping is how a real regression hides (the
    unreachable `pytest.skip` fixed in #15248). Retrying a small, FIXED number
    of times distinguishes "momentarily busy" from "persistently starved": if
    every attempt starves, this still raises, because persistent starvation is
    a fact worth a red, not noise to average away.

    WHAT THIS DOES NOT RETRY, and must not: if `measure` completes and its own
    assertion then fails — a real regression — that is a plain `AssertionError`,
    not `MeasurementStarved`, and this function does not catch it. It propagates
    on the first attempt. Retrying is scoped exclusively to "could this window
    be measured at all", so a starved attempt can never be scored as a pass —
    starvation only ever produces a retry or, on the last attempt, a distinct
    failure message naming persistent starvation rather than a budget breach.

    THE PART THIS FUNCTION CANNOT GUARANTEE ON ITS OWN, stated because a review
    of #15266 found it violated: whether "a genuine regression can never be
    masked" also holds depends on `measure` raising `MeasurementStarved` ONLY
    for a window the ENVIRONMENT emptied, never for one the operation under
    test emptied itself. A total-blockage regression — the code under test
    stalling the loop so completely that almost nothing gets measured — looks
    identical, from inside `measure`, to a runner too busy to schedule the
    heartbeat at all: both are "too few samples". A caller that raises
    `MeasurementStarved` on tick count alone, with no other signal, will retry
    that regression up to `max_attempts` times and still fail in the end —
    this function raises unconditionally once every attempt is exhausted, so
    the failure is never silently green — but the final message reads as
    environmental contention when it was actually the worst possible
    regression, and it takes `max_attempts` times as long to say so. A caller
    whose "operation under test" and "environment" can both empty the same
    window must discriminate the two BEFORE raising `MeasurementStarved`, not
    leave it to this function, which has no way to tell them apart from a
    tick count alone. `process_offload_test.py::_raise_if_a_window_starved` is
    the worked example: it brackets the measurement with an idle window on
    each side and raises `MeasurementStarved` only when the idle window is
    ALSO starved; a busy window starved while the idle windows are healthy
    means the operation under test emptied it, which is scored as an
    immediate, non-retried `AssertionError` instead.
    """
    last_reason: str | None = None
    for _attempt in range(1, max_attempts + 1):
        try:
            return await measure()
        except MeasurementStarved as starved:
            last_reason = str(starved)
    raise AssertionError(
        f"{what}: starved on all {max_attempts} attempts, last reason: "
        f"{last_reason} — the event loop was persistently unable to produce a "
        "usable measurement window, not merely busy once; this is distinct "
        "from a measured budget breach, which fails on its first attempt"
    )
