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
    company_id = str(uuid.uuid4())
    session = _mock_session()

    with patch("llc.scheduler.liveness_monitor.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.exists = AsyncMock(return_value=True)  # agent paused flag
        mock_redis.return_value = redis

        result = await monitor._agent_deliberately_paused(session, agent_id, company_id)

    assert result is True


@pytest.mark.asyncio
async def test_liveness_monitor_recovers_non_paused_agent():
    """Liveness monitor proceeds normally when no pause flag is set."""
    from llc.scheduler.liveness_monitor import LivenessMonitor

    monitor = LivenessMonitor()
    agent_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    # Redis says not paused; DB also returns no matching row
    session = _mock_session(rows=[])

    with patch("llc.scheduler.liveness_monitor.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.exists = AsyncMock(return_value=False)
        mock_redis.return_value = redis

        result = await monitor._agent_deliberately_paused(session, agent_id, company_id)

    assert result is False


# ---------------------------------------------------------------------------
# Bug #1 — liveness_monitor DB fallback for terminated agents (GH#8256 CR)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_liveness_monitor_db_fallback_skips_terminated():
    """When Redis is unavailable, DB fallback must catch terminated agents."""
    from llc.scheduler.liveness_monitor import LivenessMonitor

    monitor = LivenessMonitor()
    agent_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())

    # Redis unavailable
    session = _mock_session(rows=[("terminated",)])

    with patch("llc.scheduler.liveness_monitor.get_async_redis_client") as mock_redis:
        mock_redis.return_value = None  # Redis down

        result = await monitor._agent_deliberately_paused(session, agent_id, company_id)

    assert result is True


# ---------------------------------------------------------------------------
# Bug #2 — routine_scheduler raises when Redis None during pause re-queue (GH#8256 CR)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routine_scheduler_pause_requeue_raises_on_redis_none():
    """When Redis is None during pause re-queue, RuntimeError propagates to the
    outer except handler, which re-adds the routine with a 60s retry delay."""
    from llc.scheduler.routine_scheduler import RoutineScheduler

    scheduler = RoutineScheduler()
    routine_id_str = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    agent_id_val = str(uuid.uuid4())

    mock_routine = MagicMock()
    mock_routine.status = "active"  # RoutineStatus.ACTIVE (str enum)
    mock_routine.company_id = uuid.UUID(company_id)
    mock_routine.assignee_agent_id = uuid.UUID(agent_id_val)
    mock_routine.cron_schedule = "* * * * *"
    mock_routine.last_fired_at = None

    # Async context manager for session factory
    mock_session = AsyncMock()
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_session_cm)

    mock_svc_instance = AsyncMock()
    mock_svc_instance.get = AsyncMock(return_value=mock_routine)
    mock_svc_instance.record_run = AsyncMock()
    mock_svc_cls = MagicMock(return_value=mock_svc_instance)

    # Redis call counter:
    #  call 1 — _company_or_agent_paused: company paused flag → True
    #  call 2 — pause re-queue: returns None → raises RuntimeError
    #  call 3 — outer except re-add handler
    re_add_redis = AsyncMock()
    re_add_redis.zadd = AsyncMock()
    redis_call_count = 0

    async def redis_side_effect():
        nonlocal redis_call_count
        redis_call_count += 1
        if redis_call_count == 1:
            r = AsyncMock()
            r.exists = AsyncMock(return_value=True)
            return r
        if redis_call_count == 2:
            return None
        return re_add_redis

    with patch("user_management.database.get_async_session_factory", return_value=mock_factory):
        with patch("llc.services.routine_service.RoutineService", mock_svc_cls):
            with patch("llc.scheduler.routine_scheduler.get_async_redis_client", side_effect=redis_side_effect):
                await scheduler._dispatch_routine(routine_id_str)

    re_add_redis.zadd.assert_called_once()


# ---------------------------------------------------------------------------
# Bug #3 — resume_agent restores pre-pause status (GH#8256 CR)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initial_status",
    [
        LLCAgentStatus.ONBOARDING.value,
        LLCAgentStatus.AVAILABLE.value,
        LLCAgentStatus.ONBOARDING.value,
    ],
)
async def test_resume_agent_restores_pre_pause_status(initial_status):
    """resume_agent must restore the status that was active before pausing."""
    company_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())
    log = _activity_log_mock()
    svc = ControlsService(activity_log=log)

    call_count = 0

    def make_session_for_status(pre_pause):
        session = AsyncMock()
        result_pre = MagicMock()
        result_pre.fetchone.return_value = (LLCAgentStatus.PAUSED.value, pre_pause)
        result_update = MagicMock()
        result_update.fetchone.return_value = None

        async def execute_side(query, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return result_pre
            return result_update

        session.execute = AsyncMock(side_effect=execute_side)
        return session

    session = make_session_for_status(initial_status)

    with patch("llc.services.controls_service.get_async_redis_client") as mock_redis:
        redis = AsyncMock()
        redis.delete = AsyncMock()
        mock_redis.return_value = redis

        result = await svc.resume_agent(session, company_id, agent_id, actor_id)

    assert result["status"] == initial_status


# ---------------------------------------------------------------------------
# Bug #4 — CompanyNotFoundError raised for unknown company (GH#8256 CR)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_company_raises_company_not_found():
    """pause_company must raise CompanyNotFoundError for an unknown company_id."""
    from llc.services.controls_service import CompanyNotFoundError

    company_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())

    session = _mock_session(rows=[])  # llc_companies lookup returns nothing
    log = _activity_log_mock()
    svc = ControlsService(activity_log=log)

    with pytest.raises(CompanyNotFoundError):
        await svc.pause_company(session, company_id, actor_id)


@pytest.mark.asyncio
async def test_resume_company_raises_company_not_found():
    """resume_company must raise CompanyNotFoundError for an unknown company_id."""
    from llc.services.controls_service import CompanyNotFoundError

    company_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())

    session = _mock_session(rows=[])
    log = _activity_log_mock()
    svc = ControlsService(activity_log=log)

    with pytest.raises(CompanyNotFoundError):
        await svc.resume_company(session, company_id, actor_id)
