# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An agent switched onto the heartbeat is scheduled without a restart (#15907).

``_repopulate_schedule`` reads enabled agents only at ``start()``; before this,
a hire sent with ``heartbeat_enabled=true`` sat unscheduled until the next
process restart.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from llc.scheduler import schedule_entry
from llc.scheduler.heartbeat_scheduler import _SCHEDULE_KEY
from user_management.services import TenantContext


@pytest.mark.asyncio
async def test_an_enabled_agent_is_added_to_the_schedule_without_overwriting():
    redis = AsyncMock()
    with patch.object(schedule_entry, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        assert await schedule_entry.schedule_heartbeat("agent-1", "*/5 * * * *") is True

    key, mapping = redis.zadd.await_args.args
    assert key == _SCHEDULE_KEY
    assert list(mapping) == ["agent-1"]
    assert redis.zadd.await_args.kwargs == {"nx": True}


@pytest.mark.asyncio
async def test_no_redis_reports_not_scheduled():
    with patch.object(schedule_entry, "get_async_redis_client", new=AsyncMock(return_value=None)):
        assert await schedule_entry.schedule_heartbeat("agent-1", "*/5 * * * *") is False


@pytest.mark.asyncio
async def test_an_unusable_cron_reports_not_scheduled():
    redis = AsyncMock()
    with patch.object(schedule_entry, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        assert await schedule_entry.schedule_heartbeat("agent-1", "not a cron") is False
    redis.zadd.assert_not_awaited()


async def _hire(heartbeat_enabled: bool) -> AsyncMock:
    import llc.api.agent_hires as mod

    session = AsyncMock()
    body = mod.AgentHireRequest(agent_name="Dev", heartbeat_enabled=heartbeat_enabled)
    ctx = TenantContext(org_id=None, user_id=uuid.uuid4(), is_platform_admin=True)
    with (
        patch.object(mod, "registered_adapter_types", return_value=["claude_code"]),
        patch.object(mod, "adapter_unavailable_reason", return_value=None),
        patch.object(mod.BudgetService, "provision_budget", new=AsyncMock()),
        patch.object(mod, "schedule_heartbeat", new=AsyncMock(return_value=True)) as schedule,
    ):
        resp = await mod.hire_agent(company_id=uuid.uuid4(), body=body, session=session, ctx=ctx)
    session.commit.assert_awaited()
    schedule.agent_id = resp.agent_id
    return schedule


@pytest.mark.asyncio
async def test_a_hire_on_the_heartbeat_is_scheduled_at_once():
    import llc.api.agent_hires as mod

    schedule = await _hire(heartbeat_enabled=True)
    schedule.assert_awaited_once_with(schedule.agent_id, mod.DEFAULT_HEARTBEAT_CRON)


@pytest.mark.asyncio
async def test_a_hire_off_the_heartbeat_is_not_scheduled():
    schedule = await _hire(heartbeat_enabled=False)
    schedule.assert_not_awaited()
