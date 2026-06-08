# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for LivenessMonitor (GH#8228)."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.scheduler.liveness_monitor import LivenessMonitor, run_id_label


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
        patch("llc.scheduler.liveness_monitor.get_adapter_for_agent", new_callable=AsyncMock) as mock_adapter,
        patch("llc.scheduler.liveness_monitor.WorkItemService"),
    ):
        mock_redis.return_value = None
        mock_adapter.return_value = None

        session = AsyncMock()
        session.execute.return_value.scalars.return_value.all.return_value = [run]
        session.execute.return_value.scalar_one_or_none.return_value = None
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("llc.scheduler.liveness_monitor.get_async_session_factory", return_value=factory):
            await monitor._check_once()

    assert run.status == "timed_out"
    assert run.finished_at is not None


@pytest.mark.asyncio
async def test_checkout_lock_released_on_recovery() -> None:
    """Redis checkout lock DEL is called when work_item_id is set."""
    wid = str(uuid.uuid4())
    run = _make_run(status="running", minutes_ago=40, work_item_id=wid)

    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock()

    with (
        patch(
            "llc.scheduler.liveness_monitor.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ),
        patch("llc.scheduler.liveness_monitor.get_adapter_for_agent", new_callable=AsyncMock, return_value=None),
        patch("llc.scheduler.liveness_monitor.WorkItemService"),
    ):
        session = AsyncMock()
        session.execute.return_value.scalars.return_value.all.return_value = [run]
        session.execute.return_value.scalar_one_or_none.return_value = None
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)

        monitor = LivenessMonitor(poll_interval=9999)
        with patch("llc.scheduler.liveness_monitor.get_async_session_factory", return_value=factory):
            await monitor._check_once()

    mock_redis.delete.assert_called_once_with(f"llc:checkout:{wid}")


@pytest.mark.asyncio
async def test_adapter_cancel_called_best_effort() -> None:
    """adapter.cancel() is called when adapter is registered."""
    run = _make_run(status="running", minutes_ago=35)
    mock_adapter = AsyncMock()
    mock_adapter.cancel = AsyncMock()

    with (
        patch(
            "llc.scheduler.liveness_monitor.get_adapter_for_agent",
            new_callable=AsyncMock,
            return_value=mock_adapter,
        ),
        patch("llc.scheduler.liveness_monitor.get_async_redis_client", new_callable=AsyncMock, return_value=None),
        patch("llc.scheduler.liveness_monitor.WorkItemService"),
    ):
        session = AsyncMock()
        session.execute.return_value.scalars.return_value.all.return_value = [run]
        session.execute.return_value.scalar_one_or_none.return_value = None
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

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
            "llc.scheduler.liveness_monitor.get_adapter_for_agent",
            new_callable=AsyncMock,
            return_value=mock_adapter,
        ),
        patch("llc.scheduler.liveness_monitor.get_async_redis_client", new_callable=AsyncMock, return_value=None),
        patch("llc.scheduler.liveness_monitor.WorkItemService"),
    ):
        session = AsyncMock()
        session.execute.return_value.scalars.return_value.all.return_value = [run]
        session.execute.return_value.scalar_one_or_none.return_value = None
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

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

    asyncio.get_event_loop().run_until_complete(_run())
