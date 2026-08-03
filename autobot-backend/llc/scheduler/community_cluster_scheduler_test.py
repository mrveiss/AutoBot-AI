# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for CommunityClusteringScheduler (#13210).

Before #13210 the community-clustering loop was a hand-rolled ``while True``
in ``initialization/lifespan.py`` with two defects PR #13209 had already
fixed for LivenessMonitor/BudgetWatchdog/SessionCheckpointer:

1. ``honour_pending_cancellation()`` ran only in the ``except Exception`` arm,
   so a masked cancellation that ``CommunityClusterer.run()`` swallowed and
   returned from normally never hit the guard and re-armed a full 6-hour
   sleep. #13203 established this as the shape a per-iteration guard must
   protect against for the *other* three schedulers (each of whose ``_tick``
   provably swallows its own errors) — this file does not measure whether
   the real ``CommunityClusterer.run()`` swallows a cancellation the same
   way; ``_SwallowingClusterer`` below models that scenario so the fix is
   exercised either way.
2. Its shutdown drain was a bare, unshielded
   ``asyncio.gather(task, return_exceptions=True)`` with no timeout, so a
   tick that could never be cancelled would hang ``cleanup_services()``
   forever instead of giving up.

Subclassing ``PollLoopScheduler`` (#13210) inherits both fixes from the
already-hardened base instead of re-implementing them a second time; these
tests exercise that inheritance through the concrete subclass so a future
change that breaks the wiring (e.g. reintroducing a local except-arm-only
guard) is caught here.
"""

import asyncio
import importlib
import time
from unittest.mock import AsyncMock, patch

import pytest

from llc.scheduler.community_cluster_scheduler import CommunityClusteringScheduler


class _FakeMeshDB:
    """Placeholder passed straight through to CommunityClusterer(mesh_db)."""


def _patch_clusterer(run_coro_factory):
    """Patch the CommunityClusterer looked up by the scheduler's local import.

    Imports the target module first: ``unittest.mock.patch`` resolves a dotted
    target via ``__import__`` on the top-level package and then walks
    ``getattr`` down the remaining components, which does not reliably bind
    ``services.mesh_brain`` as an attribute of ``services`` in this suite's
    conftest, where ``services`` is a hand-built stub module with its
    ``__path__`` pointed at the real package directory rather than a normally
    imported package. Ensuring the submodule is already in ``sys.modules``
    before patching sidesteps that path entirely.
    """
    importlib.import_module("services.mesh_brain.community_clusterer")
    return patch("services.mesh_brain.community_clusterer.CommunityClusterer", run_coro_factory)


class _SwallowingClusterer:
    """Models a CommunityClusterer.run() whose DB driver masks a cancel.

    SQLAlchemy/asyncpg are known to catch BaseException while unwinding a
    connection and re-raise their own error type, which would deliver a
    cancellation into ``run()`` as an ordinary exception rather than
    ``CancelledError`` — this class stands in for that shape (not measured
    against the real ``community_clusterer.py`` call graph; see the module
    docstring) so the guard-placement fix is exercised regardless of whether
    the real code hits it today.
    """

    tick_count = 0
    tick_entered = asyncio.Event()

    def __init__(self, _mesh_db) -> None:
        pass

    async def run(self, min_weight: float = 0.3) -> list:
        type(self).tick_count += 1
        type(self).tick_entered.set()
        try:
            await asyncio.sleep(9999.0)
        except asyncio.CancelledError:
            return []  # driver consumed it; run() reports success


@pytest.mark.asyncio
async def test_swallowed_cancel_does_not_rearm_a_full_interval() -> None:
    """A masked-and-swallowed cancel must not buy the loop a fresh 6h sleep.

    Reproduces #13210 exactly: run() masks the cancel and returns normally,
    so only a per-iteration (not except-arm-only) guard can catch it.
    """
    _SwallowingClusterer.tick_count = 0
    _SwallowingClusterer.tick_entered = asyncio.Event()

    sched = CommunityClusteringScheduler(_FakeMeshDB(), poll_interval=9999.0)
    sched._first_tick = False  # skip the 300s initial delay for this test

    with _patch_clusterer(_SwallowingClusterer):
        sched.start()
        assert sched._task is not None
        await asyncio.wait_for(_SwallowingClusterer.tick_entered.wait(), timeout=1.0)

        sched._task.cancel()  # not via stop(): _running stays True

        # A re-armed 9999s inter-poll wait would blow this timeout.
        await asyncio.wait_for(asyncio.gather(sched._task, return_exceptions=True), timeout=1.0)

    assert sched._task.cancelled(), "the honoured cancel must end the task as cancelled"
    assert _SwallowingClusterer.tick_count == 1, "must not have started a second run"


class _UncancellableClusterer:
    """Models the concrete hang #13210 protects against: a tick that can
    never be cancelled because its driver retries on a dead connection."""

    tick_entered = asyncio.Event()
    mask_cancellation = True

    def __init__(self, _mesh_db) -> None:
        pass

    async def run(self, min_weight: float = 0.3) -> list:
        type(self).tick_entered.set()
        while True:
            try:
                await asyncio.sleep(9999.0)
            except asyncio.CancelledError:
                if not type(self).mask_cancellation:
                    raise
                continue


@pytest.mark.asyncio
async def test_aclose_drain_is_bounded_and_the_bound_is_measured() -> None:
    """#13210: the drain must actually terminate near its timeout, not hang.

    Measures wall-clock time rather than only asserting no exception was
    raised — proving the bound is real, not merely that aclose() returned
    (which an infinite-timeout wait_for would also do, eventually).
    """
    _UncancellableClusterer.tick_entered = asyncio.Event()
    _UncancellableClusterer.mask_cancellation = True

    sched = CommunityClusteringScheduler(_FakeMeshDB(), poll_interval=9999.0)
    sched._first_tick = False

    with _patch_clusterer(_UncancellableClusterer):
        sched.start()
        task = sched._task
        assert task is not None
        await asyncio.wait_for(_UncancellableClusterer.tick_entered.wait(), timeout=1.0)

        drain_timeout = 0.3
        start = time.monotonic()
        await asyncio.wait_for(sched.aclose(timeout=drain_timeout), timeout=3.0)
        elapsed = time.monotonic() - start

    # Bounded: settles close to the requested timeout, nowhere near the
    # 9999s the un-drained task is parked against.
    assert elapsed < drain_timeout + 1.0, f"aclose() took {elapsed:.2f}s, expected ~{drain_timeout}s"
    assert not task.done(), "the stuck task is deliberately left behind on timeout"

    # Reap it now that the measurement is taken.
    _UncancellableClusterer.mask_cancellation = False
    task.cancel()
    await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=1.0)


@pytest.mark.asyncio
async def test_first_tick_applies_the_startup_delay_only_once() -> None:
    """The 300s initial-delay sleep must run before the first clustering pass
    only, not on every iteration — preserved from the original hand-rolled
    loop's behaviour (#4834) across the #13210 refactor."""
    ran = asyncio.Event()

    class _CountingClusterer:
        def __init__(self, _mesh_db) -> None:
            pass

        async def run(self, min_weight: float = 0.3) -> list:
            ran.set()
            return []

    sched = CommunityClusteringScheduler(_FakeMeshDB(), poll_interval=9999.0)
    assert sched._first_tick is True

    # Patches this module's own `_sleep` indirection, not `asyncio.sleep` on
    # the shared asyncio module — the latter would silently no-op every other
    # coroutine's sleep in the process for the duration of this `with` block.
    mock_sleep = AsyncMock(return_value=None)
    with (
        _patch_clusterer(_CountingClusterer),
        patch("llc.scheduler.community_cluster_scheduler._sleep", mock_sleep),
    ):
        sched.start()
        # Event-gated, not timing-gated: the mocked sleep(300) is a no-op
        # coroutine that need not yield to the loop, so a blind sleep() here
        # could race the task's first step. Waiting on the real event the
        # clusterer sets is deterministic regardless of that scheduling detail.
        await asyncio.wait_for(ran.wait(), timeout=1.0)
        await sched.aclose()

    assert sched._first_tick is False
    # The initial-delay sleep(300) fires exactly once, on the first tick.
    delay_calls = [c for c in mock_sleep.call_args_list if c.args and c.args[0] == 300]
    assert len(delay_calls) == 1
