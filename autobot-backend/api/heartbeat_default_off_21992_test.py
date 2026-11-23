# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A read creates no heartbeat state, and a new state starts with the heartbeat off (#21992, #15907)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api import heartbeat
from api.heartbeat_scope import AgentScope
from models.heartbeat import AgentRuntimeState, HeartbeatStatus, WakeupTrigger
from services.heartbeat_scheduler import HeartbeatScheduler
from testkit.fake_async_session import FakeAsyncSession, FakeResult

SCOPE = AgentScope(company_id=None, platform_admin=True)


def _row(status):
    return AgentRuntimeState(agent_id="a1", status=status.value, heartbeat_interval_seconds=60)


async def _started(rows):
    session = FakeAsyncSession(results=[FakeResult(rows)])
    scheduler = HeartbeatScheduler(lambda: session)
    scheduler._spawn_task = MagicMock()
    await scheduler.start()
    return session, scheduler


@pytest.mark.asyncio
async def test_get_config_for_agent_without_row_answers_off_and_writes_nothing(monkeypatch):
    monkeypatch.setattr(heartbeat, "_paused_by_name", AsyncMock(return_value=None))
    session = FakeAsyncSession(results=[FakeResult([])])
    response = await heartbeat.get_heartbeat_config("a1", session, SCOPE)
    assert response.heartbeat_enabled is False
    assert response.status == HeartbeatStatus.DISABLED.value
    assert (session.added, session.commits, session.flushes) == ([], 0, 0)


def test_new_runtime_state_defaults_to_disabled():
    assert AgentRuntimeState.__table__.c.status.default.arg == HeartbeatStatus.DISABLED.value


@pytest.mark.asyncio
async def test_start_spawns_no_task_for_a_never_enabled_agent():
    session, scheduler = await _started([])
    scheduler._spawn_task.assert_not_called()
    assert HeartbeatStatus.ACTIVE.value in session.statements[0].compile().params.values()


@pytest.mark.asyncio
async def test_start_spawns_a_task_for_an_active_agent():
    _, scheduler = await _started([_row(HeartbeatStatus.ACTIVE)])
    scheduler._spawn_task.assert_called_once_with("a1", 60)


@pytest.mark.asyncio
async def test_event_wakeup_runs_nothing_for_a_disabled_agent():
    session = FakeAsyncSession(results=[FakeResult([HeartbeatStatus.DISABLED.value])])
    scheduler = HeartbeatScheduler(lambda: session)
    scheduler._start_run = AsyncMock()
    scheduler._invoke_agent = AsyncMock()
    await scheduler._run_once("a1", WakeupTrigger.EVENT)
    scheduler._start_run.assert_not_awaited()
    scheduler._invoke_agent.assert_not_awaited()


def _trigger_scheduler(skip):
    return MagicMock(_should_skip_heartbeat=AsyncMock(return_value=skip), _run_once=MagicMock())


@pytest.mark.asyncio
async def test_run_now_for_an_agent_that_is_not_active_answers_409(monkeypatch):
    fired = MagicMock()
    monkeypatch.setattr(heartbeat, "fire_and_forget", fired)
    with pytest.raises(HTTPException) as refused:
        await heartbeat.trigger_manual("a1", _trigger_scheduler(True), SCOPE)
    assert refused.value.status_code == 409
    fired.assert_not_called()


@pytest.mark.asyncio
async def test_run_now_for_an_active_agent_is_accepted(monkeypatch):
    fired = MagicMock()
    monkeypatch.setattr(heartbeat, "fire_and_forget", fired)
    result = await heartbeat.trigger_manual("a1", _trigger_scheduler(False), SCOPE)
    assert result == {"agent_id": "a1", "status": "triggered"}
    fired.assert_called_once()
