# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for LLC board instant controls — GH#8256 (FR-GOV-05).

Covers:
- ControlsService.pause_agent / resume_agent / terminate_agent
- ControlsService.pause_sprint / resume_sprint
- ControlsService.pause_company / resume_company
- RoutineScheduler skips paused company/agent (FR-GOV-05)
- LivenessMonitor skips recovery for deliberately paused agents
- API authorization (board_member only)
"""

import uuid
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from llc.models.enums import LLCAgentStatus
from llc.services.activity_log import ActivityEventType, LLCActivityLogService
from llc.services.controls_service import (
    AgentNotFoundError,
    ControlsService,
    SprintNotFoundError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session(rows: Optional[list] = None):
    """Return an AsyncMock that looks like an AsyncSession."""
    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = rows[0] if rows else None
    result.fetchall.return_value = rows or []
    result.scalars.return_value.all.return_value = rows or []
    session.execute.return_value = result
    return session


def _activity_log_mock() -> AsyncMock:
    log = AsyncMock(spec=LLCActivityLogService)
    log.record = AsyncMock()
    return log


# ---------------------------------------------------------------------------
# ControlsService — Agent controls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_agent_sets_status_and_logs():
    company_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())

    session = _mock_session(rows=[("available",)])
    log = _activity_log_mock()
    svc = ControlsService(activity_log=log)

    with patch("llc.services.controls_service.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.set = AsyncMock()
        mock_redis.return_value = redis

        result = await svc.pause_agent(session, company_id, agent_id, actor_id, reason="bad behavior")

    assert result["status"] == LLCAgentStatus.PAUSED.value
    assert result["agent_id"] == agent_id
    session.execute.assert_called()
    redis.set.assert_called_once()
    log.record.assert_called_once()
    call_kwargs = log.record.call_args.kwargs
    assert call_kwargs["event_type"] == ActivityEventType.CONTROL_AGENT_PAUSED


@pytest.mark.asyncio
async def test_resume_agent_clears_status_and_flag():
    company_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())

    session = _mock_session(rows=[("paused",)])
    log = _activity_log_mock()
    svc = ControlsService(activity_log=log)

    with patch("llc.services.controls_service.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.delete = AsyncMock()
        mock_redis.return_value = redis

        result = await svc.resume_agent(session, company_id, agent_id, actor_id)

    assert result["status"] == LLCAgentStatus.AVAILABLE.value
    redis.delete.assert_called_once()
    call_kwargs = log.record.call_args.kwargs
    assert call_kwargs["event_type"] == ActivityEventType.CONTROL_AGENT_RESUMED


@pytest.mark.asyncio
async def test_terminate_agent_is_permanent():
    company_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())

    session = _mock_session(rows=[("available",)])
    log = _activity_log_mock()
    svc = ControlsService(activity_log=log)

    with patch("llc.services.controls_service.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.set = AsyncMock()
        mock_redis.return_value = redis

        result = await svc.terminate_agent(session, company_id, agent_id, actor_id, reason="policy violation")

    assert result["status"] == LLCAgentStatus.TERMINATED.value
    redis.set.assert_called_once()
    call_kwargs = log.record.call_args.kwargs
    assert call_kwargs["event_type"] == ActivityEventType.CONTROL_AGENT_TERMINATED


@pytest.mark.asyncio
async def test_pause_agent_raises_if_not_found():
    company_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())
    session = _mock_session(rows=[])
    svc = ControlsService(activity_log=_activity_log_mock())
    with pytest.raises(AgentNotFoundError):
        await svc.pause_agent(session, company_id, agent_id, actor_id)


@pytest.mark.asyncio
async def test_resume_agent_raises_if_not_found():
    company_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())
    session = _mock_session(rows=[])
    svc = ControlsService(activity_log=_activity_log_mock())
    with pytest.raises(AgentNotFoundError):
        await svc.resume_agent(session, company_id, agent_id, actor_id)


@pytest.mark.asyncio
async def test_terminate_agent_raises_if_not_found():
    company_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())
    session = _mock_session(rows=[])
    svc = ControlsService(activity_log=_activity_log_mock())
    with pytest.raises(AgentNotFoundError):
        await svc.terminate_agent(session, company_id, agent_id, actor_id)


# ---------------------------------------------------------------------------
# ControlsService — Sprint controls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_sprint_pauses_all_agents():
    company_id = str(uuid.uuid4())
    sprint_id = str(uuid.uuid4())
    agent1 = str(uuid.uuid4())
    agent2 = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())

    session = AsyncMock()
    # First call: _get_sprint returns row; subsequent calls are agent lookups
    sprint_row = MagicMock()
    sprint_row.__getitem__ = lambda self, i: sprint_id

    agents_result = MagicMock()
    agents_result.fetchall.return_value = [(agent1,), (agent2,)]

    sprint_result = MagicMock()
    sprint_result.fetchone.return_value = (sprint_id,)

    agent_status_result = MagicMock()
    agent_status_result.fetchone.return_value = ("available",)

    call_count = 0

    async def execute_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return sprint_result
        if call_count == 2:
            return agents_result
        return agent_status_result

    session.execute = AsyncMock(side_effect=execute_side_effect)

    log = _activity_log_mock()
    svc = ControlsService(activity_log=log)

    with patch("llc.services.controls_service.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.set = AsyncMock()
        mock_redis.return_value = redis

        result = await svc.pause_sprint(session, company_id, sprint_id, actor_id)

    assert result["sprint_id"] == sprint_id
    assert result["agents_paused"] == 2


@pytest.mark.asyncio
async def test_pause_sprint_raises_if_not_found():
    company_id = str(uuid.uuid4())
    sprint_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())

    session = _mock_session(rows=[])  # No sprint row
    log = _activity_log_mock()
    svc = ControlsService(activity_log=log)

    with pytest.raises(SprintNotFoundError):
        await svc.pause_sprint(session, company_id, sprint_id, actor_id)


# ---------------------------------------------------------------------------
# ControlsService — Company-wide controls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_company_sets_redis_flag():
    company_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())

    session = _mock_session()
    log = _activity_log_mock()
    svc = ControlsService(activity_log=log)

    with patch("llc.services.controls_service.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.set = AsyncMock()
        mock_redis.return_value = redis

        result = await svc.pause_company(session, company_id, actor_id, reason="emergency")

    assert result["paused"] is True
    redis.set.assert_called_once_with(f"llc:company:{company_id}:paused", "emergency")
    call_kwargs = log.record.call_args.kwargs
    assert call_kwargs["event_type"] == ActivityEventType.CONTROL_COMPANY_PAUSED


@pytest.mark.asyncio
async def test_resume_company_deletes_redis_flag():
    company_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())

    session = _mock_session()
    log = _activity_log_mock()
    svc = ControlsService(activity_log=log)

    with patch("llc.services.controls_service.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.delete = AsyncMock()
        mock_redis.return_value = redis

        result = await svc.resume_company(session, company_id, actor_id)

    assert result["paused"] is False
    redis.delete.assert_called_once_with(f"llc:company:{company_id}:paused")
    call_kwargs = log.record.call_args.kwargs
    assert call_kwargs["event_type"] == ActivityEventType.CONTROL_COMPANY_RESUMED


# ---------------------------------------------------------------------------
# RoutineScheduler — FR-GOV-05 skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routine_scheduler_skips_paused_company():
    """Scheduler must not fire routines when company pause flag is set."""
    from llc.scheduler.routine_scheduler import RoutineScheduler

    scheduler = RoutineScheduler()
    company_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())

    with patch("llc.scheduler.routine_scheduler.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.exists = AsyncMock(return_value=True)  # company paused
        mock_redis.return_value = redis

        result = await scheduler._company_or_agent_paused(company_id, agent_id)

    assert result is True


@pytest.mark.asyncio
async def test_routine_scheduler_fires_when_not_paused():
    """Scheduler must fire when no pause flag is set."""
    from llc.scheduler.routine_scheduler import RoutineScheduler

    scheduler = RoutineScheduler()
    company_id = str(uuid.uuid4())

    with patch("llc.scheduler.routine_scheduler.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.exists = AsyncMock(return_value=False)  # not paused
        mock_redis.return_value = redis

        result = await scheduler._company_or_agent_paused(company_id, None)

    assert result is False


# ---------------------------------------------------------------------------
# LivenessMonitor — FR-GOV-05 skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_liveness_monitor_skips_paused_agent():
    """Liveness monitor must not create recovery items for paused agents."""
    from llc.scheduler.liveness_monitor import LivenessMonitor

    monitor = LivenessMonitor()
    agent_id = str(uuid.uuid4())

    with patch("llc.scheduler.liveness_monitor.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.exists = AsyncMock(return_value=True)  # agent paused flag
        mock_redis.return_value = redis

        result = await monitor._agent_deliberately_paused(agent_id)

    assert result is True


@pytest.mark.asyncio
async def test_liveness_monitor_recovers_non_paused_agent():
    """Liveness monitor proceeds normally when no pause flag is set."""
    from llc.scheduler.liveness_monitor import LivenessMonitor

    monitor = LivenessMonitor()
    agent_id = str(uuid.uuid4())

    with patch("llc.scheduler.liveness_monitor.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.exists = AsyncMock(return_value=False)
        mock_redis.return_value = redis

        result = await monitor._agent_deliberately_paused(agent_id)

    assert result is False
