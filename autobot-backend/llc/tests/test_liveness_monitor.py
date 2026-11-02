# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for LivenessMonitor (GH#8228)."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.redis_utils import COMPARE_AND_DELETE_LUA
from llc.models.activity import ActorType, LLCActivityLog
from llc.models.enums import ActivityEventType
from llc.scheduler.liveness_monitor import LivenessMonitor, run_id_label
from llc.services.activity_log import LLCActivityLogService
from testkit.fake_async_session import FakeAsyncSession, FakeResult


class _Savepoint:
    """What ``session.begin_nested()`` returns on the AsyncMock sessions below: a SAVEPOINT that never fails."""

    async def __aenter__(self) -> "_Savepoint":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


@pytest.fixture(autouse=True)
def _no_live_publish():  # noqa: ANN202
    """The monitor now audits through a real log; its pub/sub fan-out is not under test here."""
    with patch.object(LLCActivityLogService, "_deliver", AsyncMock()):
        yield


def _mock_session(stuck_runs: list, work_item: object | None = None) -> AsyncMock:
    """Build an async session mock whose execute() returns a *sync* result.

    ``AsyncMock`` propagates async to its children, so the naive
    ``session.execute.return_value.scalars()`` yields a coroutine, not a row
    set. Configure execute() to return an explicit MagicMock instead so
    ``.scalars().all()`` / ``.scalar_one_or_none()`` / ``.fetchone()`` work.
    """
    result = MagicMock()
    result.scalars.return_value.all.return_value = stuck_runs
    result.scalar_one_or_none.return_value = work_item
    result.fetchone.return_value = None  # _agent_deliberately_paused DB fallback
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.begin_nested = MagicMock(side_effect=lambda: _Savepoint())
    return session


def _make_run(
    status: str = "running",
    minutes_ago: int = 35,
    work_item_id: str | None = None,
) -> MagicMock:
    run = MagicMock()
    run.id = uuid.uuid4()
    run.agent_id = "agent-001"
    run.company_id = uuid.uuid4()
    run.status = status
    run.started_at = datetime.now(tz=timezone.utc) - timedelta(minutes=minutes_ago)
    run.finished_at = None
    run.work_item_id = uuid.UUID(work_item_id) if work_item_id else None
    return run


def _make_session(runs: list) -> AsyncMock:
    session = AsyncMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = runs
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_result
    # second call (for work_item lookup) returns None
    execute_result.scalar_one_or_none.return_value = None
    session.execute.return_value = execute_result
    return session


@pytest.mark.asyncio
async def test_no_stuck_runs_is_noop() -> None:
    """When there are no stuck runs, no DB mutations or Redis calls happen."""
    monitor = LivenessMonitor(poll_interval=9999)
    session = _make_session([])

    with patch("llc.scheduler.liveness_monitor.get_async_session_factory") as mock_factory:
        factory_instance = MagicMock()
        factory_instance.return_value.__aenter__ = AsyncMock(return_value=session)
        factory_instance.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = factory_instance

        await monitor._check_once()

    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_stuck_run_marked_timed_out() -> None:
    """A stuck run gets status=timed_out and finished_at set."""
    run = _make_run(status="running", minutes_ago=35)
    monitor = LivenessMonitor(poll_interval=9999)

    with (
        patch("llc.scheduler.liveness_monitor.get_async_redis_client", new_callable=AsyncMock) as mock_redis,
        patch("llc.adapters.get_adapter_for_agent", new_callable=AsyncMock) as mock_adapter,
        patch("llc.scheduler.liveness_monitor.WorkItemService"),
    ):
        mock_redis.return_value = None
        mock_adapter.return_value = None

        session = _mock_session([run])

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("llc.scheduler.liveness_monitor.get_async_session_factory", return_value=factory):
            await monitor._check_once()

    assert run.status == "timed_out"
    assert run.finished_at is not None


@pytest.mark.asyncio
async def test_checkout_lock_released_on_recovery() -> None:
    """The checkout fence is released, compare-and-delete on the run's agent, when work_item_id is set."""
    wid = str(uuid.uuid4())
    run = _make_run(status="running", minutes_ago=40, work_item_id=wid)

    mock_redis = AsyncMock()
    mock_redis.eval = AsyncMock(return_value=1)
    # exists() must be falsy or _agent_deliberately_paused() treats the agent as
    # paused and skips the recovery flow under test.
    mock_redis.exists = AsyncMock(return_value=0)

    with (
        patch(
            "llc.scheduler.liveness_monitor.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ),
        patch("llc.adapters.get_adapter_for_agent", new_callable=AsyncMock, return_value=None),
        patch("llc.scheduler.liveness_monitor.WorkItemService"),
    ):
        session = _mock_session([run])

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)

        monitor = LivenessMonitor(poll_interval=9999)
        with patch("llc.scheduler.liveness_monitor.get_async_session_factory", return_value=factory):
            await monitor._check_once()

    mock_redis.eval.assert_called_once_with(COMPARE_AND_DELETE_LUA, 1, f"llc:checkout:{wid}", run.agent_id)
    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_adapter_cancel_called_best_effort() -> None:
    """adapter.cancel() is called when adapter is registered."""
    run = _make_run(status="running", minutes_ago=35)
    mock_adapter = AsyncMock()
    mock_adapter.cancel = AsyncMock()

    with (
        patch(
            "llc.adapters.get_adapter_for_agent",
            new_callable=AsyncMock,
            return_value=mock_adapter,
        ),
        patch("llc.scheduler.liveness_monitor.get_async_redis_client", new_callable=AsyncMock, return_value=None),
        patch("llc.scheduler.liveness_monitor.WorkItemService"),
    ):
        session = _mock_session([run])

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)

        monitor = LivenessMonitor(poll_interval=9999)
        with patch("llc.scheduler.liveness_monitor.get_async_session_factory", return_value=factory):
            await monitor._check_once()

    mock_adapter.cancel.assert_called_once_with({}, str(run.id))


@pytest.mark.asyncio
async def test_adapter_cancel_exception_is_swallowed() -> None:
    """Exceptions from adapter.cancel() do not abort the recovery flow."""
    run = _make_run(status="running", minutes_ago=35)
    mock_adapter = AsyncMock()
    mock_adapter.cancel = AsyncMock(side_effect=RuntimeError("adapter down"))

    with (
        patch(
            "llc.adapters.get_adapter_for_agent",
            new_callable=AsyncMock,
            return_value=mock_adapter,
        ),
        patch("llc.scheduler.liveness_monitor.get_async_redis_client", new_callable=AsyncMock, return_value=None),
        patch("llc.scheduler.liveness_monitor.WorkItemService"),
    ):
        session = _mock_session([run])

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)

        monitor = LivenessMonitor(poll_interval=9999)
        with patch("llc.scheduler.liveness_monitor.get_async_session_factory", return_value=factory):
            await monitor._check_once()

    # Status was still updated despite adapter failure
    assert run.status == "timed_out"


def test_run_id_label() -> None:
    """run_id_label returns a short human-readable prefix."""
    label = run_id_label("12345678-abcd-0000-0000-000000000000")
    assert label == "run:12345678"


def test_monitor_start_stop() -> None:
    """LivenessMonitor.start() creates a task; stop() cancels it."""
    import asyncio

    async def _run():
        monitor = LivenessMonitor(poll_interval=9999)
        with patch("llc.scheduler.liveness_monitor.get_async_session_factory"):
            monitor.start()
            assert monitor._task is not None
            assert not monitor._task.done()
            monitor.stop()
            assert not monitor._running

    # #13113: asyncio.run() — pytest-asyncio owns the loop lifecycle, so a sync test
    # running before any async test on its worker had no current loop for get_event_loop().
    asyncio.run(_run())


# --- the audit write (#20101) -----------------------------------------------------------------


def test_the_monitor_has_a_real_log_when_none_is_passed() -> None:
    assert isinstance(LivenessMonitor()._activity_log, LLCActivityLogService)


def _fake_scan(runs: list) -> FakeAsyncSession:
    """A session whose first query finds *runs*; every later one finds nothing."""
    return FakeAsyncSession(assign_ids=uuid.uuid4, results=[FakeResult(runs)], default_result=FakeResult([]))


def _audit_rows(session: FakeAsyncSession) -> list:
    return [obj for obj in session.added if isinstance(obj, LLCActivityLog)]


async def _scan(monitor: LivenessMonitor, session: FakeAsyncSession, adapter: AsyncMock) -> None:
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    with (
        patch("llc.scheduler.liveness_monitor.get_async_session_factory", return_value=factory),
        patch("llc.scheduler.liveness_monitor.agent_ref_block_reason", AsyncMock(return_value=None)),
        patch("llc.scheduler.liveness_monitor.get_async_redis_client", AsyncMock(return_value=None)),
        patch("llc.scheduler.liveness_monitor.WorkItemService", return_value=MagicMock(create=AsyncMock())),
        patch("llc.adapters.get_adapter_for_agent", AsyncMock(return_value=adapter)),
    ):
        await monitor._check_once()


@pytest.mark.asyncio
async def test_the_recovery_audits_as_the_system_under_a_real_run_id() -> None:
    run = _make_run()
    monitor = LivenessMonitor(poll_interval=9999)
    session = _fake_scan([run])
    await _scan(monitor, session, AsyncMock())
    (row,) = _audit_rows(session)
    assert (row.actor_type, row.actor_agent_id, row.actor_user_id) == (ActorType.SYSTEM.value, None, None)
    assert (row.action, row.entity_type, row.entity_id) == (
        ActivityEventType.HEARTBEAT_FAILED.value,
        "heartbeat_run",
        run.id,
    )
    assert session.commits == 1


@pytest.mark.asyncio
async def test_a_failed_audit_undoes_that_run_alone_and_the_other_runs_still_recover() -> None:
    first, second = _make_run(), _make_run()
    monitor = LivenessMonitor(poll_interval=9999)
    real_record = monitor._activity_log.record
    calls = {"n": 0}

    async def fail_once(*args: object, **kwargs: object):  # noqa: ANN202
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("audit store down")
        return await real_record(*args, **kwargs)

    monitor._activity_log.record = fail_once
    session, adapter = _fake_scan([first, second]), AsyncMock()
    await _scan(monitor, session, adapter)
    assert adapter.cancel.await_count == 1, "the failed run must not have cancelled its adapter"
    adapter.cancel.assert_awaited_once_with({}, str(second.id))
    assert session.rollbacks == 1 and session.commits == 1
    assert [row.entity_id for row in _audit_rows(session)] == [second.id]
