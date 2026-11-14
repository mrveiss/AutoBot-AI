# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed reschedule AFTER the adapter task started must not run the agent twice (#20117 AC3).

``_dispatch_due`` requeues an agent whose handler raised, one poll later. Before the run
starts that is right; once it has started, the requeue is a second run. The schedule
reconciler restores the missing member instead, as it does for a routine.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.scheduler.heartbeat_scheduler import _SCHEDULE_KEY, LLCHeartbeatScheduler
from testkit.fake_async_session import FakeAsyncSession

_HBS = "llc.scheduler.heartbeat_scheduler"
_AGENT_SLUG = "ceo-acme"
_AGENT = {
    "agent_id": _AGENT_SLUG,
    "company_id": "company-1",
    "heartbeat_cron": "* * * * *",
    "adapter_type": "claude_code",
    "adapter_config": {},
}


def _redis(zadd: AsyncMock) -> MagicMock:
    redis = MagicMock()
    redis.zrangebyscore = AsyncMock(return_value=[_AGENT_SLUG])
    redis.zrem = AsyncMock(return_value=1)
    redis.zadd = zadd
    return redis


def _factory() -> MagicMock:
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=FakeAsyncSession())
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


async def _tick(scheduler: LLCHeartbeatScheduler, redis: MagicMock, run_adapter: AsyncMock) -> None:
    run = MagicMock(id=uuid.uuid4(), context_snapshot=None, retry_count=0)
    with (
        patch(f"{_HBS}.get_async_redis_client", AsyncMock(return_value=redis)),
        patch.object(scheduler, "_get_agent_config", AsyncMock(return_value=dict(_AGENT))),
        patch.object(scheduler, "_find_rate_limited_run", AsyncMock(return_value=None)),
        patch.object(scheduler, "_create_run", AsyncMock(return_value=run)),
        patch.object(scheduler, "_run_adapter", run_adapter),
        patch(f"{_HBS}.dispatch_block_reason", AsyncMock(return_value=None)),
        patch(f"{_HBS}.has_pending_work", AsyncMock(return_value=True)),
        patch(f"{_HBS}.acquire_run_workspace", AsyncMock(return_value=True)),
        patch(f"{_HBS}.enrich_run_context", AsyncMock()),
        patch(f"{_HBS}.get_async_session_factory", return_value=_factory()),
    ):
        await scheduler._dispatch_due()
        for task in list(scheduler._tasks):
            await task


@pytest.mark.asyncio
async def test_failed_reschedule_after_a_started_run_is_not_requeued(caplog: Any) -> None:
    zadd = AsyncMock(side_effect=RuntimeError("redis down"))
    redis, run_adapter, scheduler = _redis(zadd), AsyncMock(), LLCHeartbeatScheduler()
    with caplog.at_level(logging.ERROR, logger="llc.scheduler.schedule_members"):
        await _tick(scheduler, redis, run_adapter)

    assert run_adapter.await_count == 1  # the one dispatch
    assert zadd.await_count == 1  # only the failed reschedule; no `_requeue` re-add one poll later
    assert redis.zadd.await_args.args[0] == _SCHEDULE_KEY
    assert "rescheduling failed" in caplog.text and "reconciler will restore" in caplog.text


@pytest.mark.asyncio
async def test_a_failure_before_the_run_starts_is_still_requeued() -> None:
    """The contrast case: nothing ran, so the requeue is the right recovery."""
    zadd = AsyncMock()
    redis, run_adapter, scheduler = _redis(zadd), AsyncMock(), LLCHeartbeatScheduler()
    with patch.object(scheduler, "_handle_due_agent", AsyncMock(side_effect=RuntimeError("before start"))):
        with patch(f"{_HBS}.get_async_redis_client", AsyncMock(return_value=redis)):
            await scheduler._dispatch_due()

    run_adapter.assert_not_awaited()
    assert zadd.await_count == 1  # the requeue
