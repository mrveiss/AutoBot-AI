# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Tests for lifespan shutdown ordering (#11679) and scheduler drain (#13085).

Covers the fast-shutdown race between phase-2 background initialization and
cleanup_services(), the executor-drain-before-Redis-close ordering, and the
awaited drain of the LLC poll-loop schedulers.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import initialization.lifespan as lifespan_module
from initialization.lifespan import cleanup_services


@pytest.mark.asyncio
async def test_cleanup_cancels_background_init_task_first():
    """Fast-shutdown race (#11679): the phase-2 task must be cancelled and
    awaited before any other cleanup step, and must not leak as an orphan
    task once cleanup_services() returns."""
    still_running = asyncio.Event()

    async def _slow_phase2() -> None:
        still_running.set()
        await asyncio.sleep(30)

    task = asyncio.create_task(_slow_phase2(), name="phase2_background_init")
    await still_running.wait()

    app = SimpleNamespace(state=SimpleNamespace(background_init_task=task))

    with (
        patch("autobot_shared.redis_client.close_all_redis_connections", new=AsyncMock()),
        patch.object(lifespan_module, "shutdown_tracing", new=AsyncMock()),
    ):
        await cleanup_services(app)

    assert task.done()
    assert task.cancelled()
    # No orphan phase-2 task left running after cleanup completes.
    remaining = [t for t in asyncio.all_tasks() if t.get_name() == "phase2_background_init"]
    assert remaining == []


@pytest.mark.asyncio
async def test_cleanup_drains_executor_before_redis_close():
    """Ordering decision (#11679): the bounded thread-pool executor must be
    drained BEFORE Redis pools close, so queued sync jobs (e.g.
    chat_history/cache.py's setex offload) cannot touch Redis after the
    pools are gone."""
    call_order: list[str] = []

    executor = ThreadPoolExecutor(max_workers=1)
    lifespan_module._executor = executor

    async def _fake_redis_close() -> None:
        call_order.append("redis_close")

    def _fake_shutdown(*_args, **_kwargs) -> None:
        call_order.append("executor_shutdown")

    app = SimpleNamespace(state=SimpleNamespace())

    with (
        patch("autobot_shared.redis_client.close_all_redis_connections", new=_fake_redis_close),
        patch.object(executor, "shutdown", side_effect=_fake_shutdown),
        patch.object(lifespan_module, "shutdown_tracing", new=AsyncMock()),
    ):
        await cleanup_services(app)

    assert call_order == ["executor_shutdown", "redis_close"]

    lifespan_module._executor = None


@pytest.mark.asyncio
async def test_cleanup_drains_llc_poll_schedulers():
    """#13085: the three LLC poll-loop schedulers must be *drained*, not just
    asked to stop.

    ``PollLoopScheduler.stop()`` only requests cancellation and returns, so the
    poll task could still be mid-tick — holding an AsyncSession — when
    close_database() disposes the engine later in the same cleanup, and its
    inter-poll wait was left for whoever tore the event loop down. Shutdown must
    await ``aclose()`` for every one of them.
    """
    monitor = SimpleNamespace(aclose=AsyncMock(), stop=lambda: None)
    watchdog = SimpleNamespace(aclose=AsyncMock(), stop=lambda: None)
    checkpointer = SimpleNamespace(aclose=AsyncMock(), stop=lambda: None)

    app = SimpleNamespace(
        state=SimpleNamespace(
            llc_liveness_monitor=monitor,
            llc_budget_watchdog=watchdog,
            llc_session_checkpointer=checkpointer,
        )
    )

    with (
        patch("autobot_shared.redis_client.close_all_redis_connections", new=AsyncMock()),
        patch.object(lifespan_module, "shutdown_tracing", new=AsyncMock()),
    ):
        await cleanup_services(app)

    monitor.aclose.assert_awaited_once()
    watchdog.aclose.assert_awaited_once()
    checkpointer.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_drains_community_cluster_scheduler():
    """#13210: the community-clustering scheduler must be drained via aclose()
    like its three sibling schedulers, not fired-and-forgotten with a bare
    ``task.cancel()`` + unbounded ``asyncio.gather()`` (the pre-#13210 shape)."""
    scheduler = SimpleNamespace(aclose=AsyncMock(), stop=lambda: None)
    app = SimpleNamespace(state=SimpleNamespace(community_cluster_scheduler=scheduler))

    with (
        patch("autobot_shared.redis_client.close_all_redis_connections", new=AsyncMock()),
        patch.object(lifespan_module, "shutdown_tracing", new=AsyncMock()),
    ):
        await cleanup_services(app)

    scheduler.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_community_clustering_loop_actually_starts_a_scheduler():
    """#13085: prove the wiring starts the scheduler rather than merely
    asserting it exists in source — nothing in the suite previously drove
    ``initialize_background_services`` far enough to start these schedulers,
    so a green suite was not evidence any of them ran (#13085's reopen)."""
    from initialization.lifespan import _start_community_clustering_loop

    app = SimpleNamespace(state=SimpleNamespace(mesh_db=object()))

    await _start_community_clustering_loop(app)

    scheduler = app.state.community_cluster_scheduler
    assert scheduler is not None
    assert scheduler.is_running, "the scheduler must actually be started, not merely constructed"

    await scheduler.aclose()


@pytest.mark.asyncio
async def test_start_community_clustering_loop_skips_without_mesh_db():
    """No mesh_db on app.state (GraphRAG disabled) must not start a scheduler
    that would immediately fail every tick."""
    from initialization.lifespan import _start_community_clustering_loop

    app = SimpleNamespace(state=SimpleNamespace())  # no mesh_db attribute

    await _start_community_clustering_loop(app)

    assert getattr(app.state, "community_cluster_scheduler", None) is None


@pytest.mark.asyncio
async def test_cleanup_drain_uses_the_real_scheduler_contract():
    """The drain wired into cleanup_services matches PollLoopScheduler's own API.

    Guards against the mock-only version of the test above passing while the
    real schedulers grow a different method name.
    """
    from llc.scheduler.base import PollLoopScheduler

    class _Sched(PollLoopScheduler):
        async def _tick(self) -> None:
            await asyncio.sleep(0)

    sched = _Sched(poll_interval=9999.0)
    sched.start()
    task = sched._task

    app = SimpleNamespace(state=SimpleNamespace(llc_budget_watchdog=sched))

    with (
        patch("autobot_shared.redis_client.close_all_redis_connections", new=AsyncMock()),
        patch.object(lifespan_module, "shutdown_tracing", new=AsyncMock()),
    ):
        await asyncio.wait_for(cleanup_services(app), timeout=5.0)

    assert task is not None and task.done(), "cleanup must leave no live poll task"
    assert not sched.is_running


@pytest.mark.asyncio
async def test_cleanup_drain_of_stuck_community_scheduler_is_bounded_and_measured():
    """#13210: cleanup_services() must not hang forever on a community-cluster
    tick that cannot be cancelled (a masked cancel retried against a dead
    connection, #13203's concrete failure mode). Measures wall-clock time
    rather than only asserting no exception, proving the bound is real.

    ``cleanup_services()`` calls ``scheduler.aclose()`` with no explicit
    timeout, so it uses whatever the scheduler's own ``aclose()`` resolves —
    overridden here to a small value so the test proves the bound is honoured
    end-to-end through the real cleanup path without waiting out the
    production default.
    """
    import time

    from llc.scheduler.base import PollLoopScheduler

    tick_entered = asyncio.Event()

    class _UncancellableScheduler(PollLoopScheduler):
        async def _tick(self) -> None:
            tick_entered.set()
            while True:
                try:
                    await asyncio.sleep(9999.0)
                except asyncio.CancelledError:
                    continue  # models a driver that swallows every cancel

        async def aclose(self, timeout: float = 0.2) -> None:
            await super().aclose(timeout)

    sched = _UncancellableScheduler(poll_interval=9999.0)
    sched.start()
    task = sched._task
    await asyncio.wait_for(tick_entered.wait(), timeout=1.0)

    app = SimpleNamespace(state=SimpleNamespace(community_cluster_scheduler=sched))

    with (
        patch("autobot_shared.redis_client.close_all_redis_connections", new=AsyncMock()),
        patch.object(lifespan_module, "shutdown_tracing", new=AsyncMock()),
    ):
        start = time.monotonic()
        await asyncio.wait_for(cleanup_services(app), timeout=3.0)
        elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"cleanup_services() took {elapsed:.2f}s, expected to settle near the 0.2s bound"
    assert not task.done(), "the uncancellable task is deliberately left behind, not force-killed"

    # Reap it so the test process doesn't leak a background task.
    task.cancel()
    for _ in range(3):
        await asyncio.sleep(0)
