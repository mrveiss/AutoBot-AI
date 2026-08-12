# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Tests for lifespan shutdown ordering (#11679) and scheduler drain (#13085).

Covers the fast-shutdown race between phase-2 background initialization and
cleanup_services(), the executor-drain-before-Redis-close ordering, and the
awaited drain of the LLC poll-loop schedulers.
"""

import asyncio
import contextlib
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import initialization.lifespan as lifespan_module
from initialization.lifespan import cleanup_services


@contextlib.contextmanager
def _stub_slow_cleanup_legs():
    """Stub cleanup_services()'s unconditional (not hasattr-gated) real-I/O
    calls that are unrelated to the LLC scheduler drain under test (#13284:
    the suite budgets zero tests over 10s; these legs can hit real network
    connect timeouts depending on environment, which has nothing to do with
    what these tests assert)."""
    handoff_svc = MagicMock()
    handoff_svc.shutdown = AsyncMock()
    connector_scheduler = MagicMock()
    connector_scheduler.stop_all = AsyncMock()

    with (
        patch.object(lifespan_module, "shutdown_slm_client", new=AsyncMock()),
        patch("services.documentation_watcher.stop_documentation_watcher", new=AsyncMock()),
        patch("services.kb_folder_watcher.stop_kb_folder_watcher", new=AsyncMock()),
        patch("llc.api.work_items._get_handoff_service", return_value=handoff_svc),
        patch("workflow_scheduler.stop_autonomous_loop", new=AsyncMock()),
        patch("api.analytics.analytics_controller.metrics_collector.stop_collection", new=AsyncMock()),
        patch("knowledge.connectors.scheduler.get_connector_scheduler", return_value=connector_scheduler),
    ):
        yield


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
        _stub_slow_cleanup_legs(),
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
async def test_init_liveness_monitor_actually_starts_it():
    """#13085: same proof as the community-clustering test above, for the
    other two named schedulers — LivenessMonitor and BudgetWatchdog are also
    never exercised past construction anywhere in the suite."""
    from initialization.lifespan import _init_liveness_monitor

    app = SimpleNamespace(state=SimpleNamespace())

    await _init_liveness_monitor(app)

    monitor = app.state.llc_liveness_monitor
    assert monitor is not None
    assert monitor.is_running, "LivenessMonitor must actually be started, not merely constructed"

    await monitor.aclose()


@pytest.mark.asyncio
async def test_init_budget_watchdog_actually_starts_it():
    """#13085: BudgetWatchdog counterpart of the LivenessMonitor test above."""
    from initialization.lifespan import _init_budget_watchdog

    app = SimpleNamespace(state=SimpleNamespace())

    await _init_budget_watchdog(app)

    watchdog = app.state.llc_budget_watchdog
    assert watchdog is not None
    assert watchdog.is_running, "BudgetWatchdog must actually be started, not merely constructed"

    await watchdog.aclose()


@pytest.mark.asyncio
async def test_health_probe_reports_liveness_monitor_and_checkpointer_running_via_real_lifespan():
    """#13331: llc/health/probe.py used to build its own private,
    never-started LivenessMonitor/SessionCheckpointer singletons instead of
    reading the ones lifespan actually starts and stores on app.state, so
    the probe permanently reported them as not running. Asserting against a
    mock would not catch that class of bug -- the objects here are started
    through the REAL production init functions (same precedent as
    test_init_liveness_monitor_actually_starts_it above), and the probe must
    report them running.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from initialization.lifespan import _init_liveness_monitor, _init_session_checkpointer
    from llc.health.probe import probe_llc

    app = SimpleNamespace(state=SimpleNamespace())
    await _init_liveness_monitor(app)
    await _init_session_checkpointer(app)

    request = MagicMock()
    request.app = app

    # Only the DB/Redis-backed metrics unrelated to this regression are
    # stubbed -- the liveness-monitor/session-checkpointer wiring under test
    # runs for real.
    try:
        with (
            patch("llc.health.probe._count_overdue_agents", new=AsyncMock(return_value=(0, 0))),
            patch("llc.health.probe._budget_counts", new=AsyncMock(return_value=(0, 0))),
            patch("llc.health.probe._pending_approvals_critical", new=AsyncMock(return_value=0)),
            patch("llc.health.probe._count_agents_missing_instructions", new=AsyncMock(return_value=0)),
            patch("llc.health.probe._scheduler_tick_age", new=AsyncMock(return_value=None)),
            patch("llc.health.probe._session_recovery_available", new=AsyncMock(return_value=False)),
        ):
            result = await probe_llc(request)

        assert result.data["liveness_monitor_wired"] is True
        assert (
            result.data["liveness_monitor_running"] is True
        ), "must report the object lifespan actually started, not a disconnected shadow (GH#13331)"
        assert result.data["session_checkpointer_wired"] is True
        assert (
            result.data["session_checkpointer_running"] is True
        ), "must report the object lifespan actually started, not a disconnected shadow (GH#13331)"
    finally:
        await app.state.llc_liveness_monitor.aclose()
        await app.state.llc_session_checkpointer.aclose()


@pytest.mark.asyncio
async def test_health_probe_reports_wired_but_not_running_after_real_shutdown():
    """#13331: a component lifespan started and then stopped (aclose()) is
    wired=True, running=False -- degraded, not down. Distinct from the
    unwired case (no request / app.state never got the attribute), which is
    the whole point of this fix -- see llc/tests/test_health_probe.py's
    _app_state_scheduler_state unit tests for the unwired-vs-not-running
    matrix."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from initialization.lifespan import _init_liveness_monitor
    from llc.health.probe import probe_llc

    app = SimpleNamespace(state=SimpleNamespace())
    await _init_liveness_monitor(app)
    await app.state.llc_liveness_monitor.aclose()

    request = MagicMock()
    request.app = app

    with (
        patch("llc.health.probe._count_overdue_agents", new=AsyncMock(return_value=(0, 0))),
        patch("llc.health.probe._budget_counts", new=AsyncMock(return_value=(0, 0))),
        patch("llc.health.probe._pending_approvals_critical", new=AsyncMock(return_value=0)),
        patch("llc.health.probe._count_agents_missing_instructions", new=AsyncMock(return_value=0)),
        patch("llc.health.probe._scheduler_tick_age", new=AsyncMock(return_value=None)),
        patch("llc.health.probe._session_recovery_available", new=AsyncMock(return_value=False)),
    ):
        result = await probe_llc(request)

    assert result.data["liveness_monitor_wired"] is True
    assert result.data["liveness_monitor_running"] is False


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

    Times ``scheduler.aclose()`` itself via a spy, not the whole
    ``cleanup_services(app)`` call — the latter also runs Redis close,
    tracing shutdown, and every other teardown step, so wrapping the full
    call couples this assertion to their combined latency instead of the one
    thing #13210 bounds.

    The stuck task can never honour a real cancellation (that is the whole
    point of the scenario, mirroring #13203's dead-connection retry), so it
    cannot be reaped the way a normal task is. ``mask_cancellation`` is
    flipped off after the measurement — mirroring
    ``community_cluster_scheduler_test.py``'s ``_UncancellableClusterer`` —
    so the reap in the ``finally`` block can actually succeed instead of
    leaving a live task for pytest-asyncio's loop teardown to hang on.
    """
    import time

    from llc.scheduler.base import PollLoopScheduler

    tick_entered = asyncio.Event()

    class _UncancellableScheduler(PollLoopScheduler):
        mask_cancellation = True

        async def _tick(self) -> None:
            tick_entered.set()
            while True:
                try:
                    await asyncio.sleep(9999.0)
                except asyncio.CancelledError:
                    if not type(self).mask_cancellation:
                        raise
                    continue  # models a driver that swallows every cancel

        async def aclose(self, timeout: float = 0.2) -> None:
            await super().aclose(timeout)

    sched = _UncancellableScheduler(poll_interval=9999.0)
    sched.start()
    task = sched._task
    await asyncio.wait_for(tick_entered.wait(), timeout=1.0)

    aclose_elapsed: list[float] = []
    real_aclose = sched.aclose

    async def _timed_aclose(*args, **kwargs) -> None:
        start = time.monotonic()
        try:
            await real_aclose(*args, **kwargs)
        finally:
            aclose_elapsed.append(time.monotonic() - start)

    sched.aclose = _timed_aclose

    app = SimpleNamespace(state=SimpleNamespace(community_cluster_scheduler=sched))

    try:
        with (
            patch("autobot_shared.redis_client.close_all_redis_connections", new=AsyncMock()),
            patch.object(lifespan_module, "shutdown_tracing", new=AsyncMock()),
            _stub_slow_cleanup_legs(),
        ):
            await asyncio.wait_for(cleanup_services(app), timeout=3.0)

        assert aclose_elapsed, "cleanup_services() must have called scheduler.aclose()"
        assert (
            aclose_elapsed[0] < 1.0
        ), f"aclose() itself took {aclose_elapsed[0]:.2f}s, expected to settle near its 0.2s bound"
        assert not task.done(), "the uncancellable task is deliberately left behind, not force-killed"
    finally:
        # Only now does the task honour a cancel — reap it so the test
        # process doesn't leak a background task into pytest-asyncio's loop
        # teardown, even if an assertion above failed.
        _UncancellableScheduler.mask_cancellation = False
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=1.0)
