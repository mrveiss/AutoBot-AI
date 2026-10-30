# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An over-budget, paused or terminated agent never starts a run (#19240)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import LLCRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.scheduler.dispatch_gate import (
    AgentNotDispatchable,
    agent_ref_block_reason,
    dispatch_block_reason,
    require_dispatchable,
)
from llc.scheduler.heartbeat_scheduler import LLCHeartbeatScheduler

_GATE = "llc.scheduler.dispatch_gate"
_HBS = "llc.scheduler.heartbeat_scheduler"
_COMPANY_ID = str(uuid.uuid4())
_SLUG = "ceo-acme"


def _redis(*paused_keys: str) -> AsyncMock:
    redis = AsyncMock()
    redis.exists = AsyncMock(side_effect=lambda key: key in paused_keys)
    return redis


def _budget(over_limit: bool) -> MagicMock:
    service = MagicMock()
    service.return_value.check_budget = AsyncMock(return_value=(Decimal("0"), over_limit, over_limit))
    return service


async def _reason(status="available", *, paused=(), over_limit=False, **kwargs):
    with (
        patch(f"{_GATE}.get_async_redis_client", AsyncMock(return_value=_redis(*paused))),
        patch(f"{_GATE}.BudgetService", _budget(over_limit)),
    ):
        return await dispatch_block_reason(AsyncMock(), _SLUG, _COMPANY_ID, status, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["paused", "inactive", "terminated"])
async def test_a_stopped_status_is_refused(status):
    assert await _reason(status) == f"agent status is {status}"


@pytest.mark.asyncio
async def test_an_exhausted_budget_is_refused_before_the_run():
    assert await _reason(over_limit=True) == "budget is exhausted"


@pytest.mark.asyncio
async def test_pause_all_refuses_every_agent_of_the_company():
    assert await _reason(paused=[f"llc:company:{_COMPANY_ID}:paused"]) == "company is paused"


@pytest.mark.asyncio
async def test_the_agent_pause_flag_is_refused():
    assert await _reason(paused=[f"llc:agent:{_SLUG}:paused"]) == "agent is paused"


@pytest.mark.asyncio
async def test_a_healthy_agent_passes():
    assert await _reason() is None


@pytest.mark.asyncio
async def test_a_budget_read_failure_refuses_rather_than_runs():
    service = MagicMock()
    service.return_value.check_budget = AsyncMock(side_effect=RuntimeError("db down"))
    with (
        patch(f"{_GATE}.get_async_redis_client", AsyncMock(return_value=_redis())),
        patch(f"{_GATE}.BudgetService", service),
        pytest.raises(RuntimeError),
    ):
        await dispatch_block_reason(AsyncMock(), _SLUG, _COMPANY_ID, "available")


@pytest.mark.asyncio
async def test_liveness_still_recovers_a_dead_run_during_a_company_pause():
    assert await _reason(paused=[f"llc:company:{_COMPANY_ID}:paused"], deliberate_only=True) is None


@pytest.mark.asyncio
async def test_liveness_still_recovers_a_budget_stopped_agents_dead_run():
    """``inactive`` and an exhausted budget are not deliberate: its claims must still be released."""
    assert await _reason("inactive", over_limit=True, deliberate_only=True) is None
    assert await _reason("terminated", deliberate_only=True) == "agent status is terminated"


@pytest.mark.asyncio
async def test_a_routine_holding_the_node_uuid_reads_the_slugs_pause_flag():
    """Routines hold ``AgentOrgNode.id``; controls write the flag under the slug."""
    node_pk = str(uuid.uuid4())
    session = AsyncMock()
    session.execute.return_value = MagicMock(first=MagicMock(return_value=(_SLUG, "available")))
    with patch(
        f"{_GATE}.get_async_redis_client",
        AsyncMock(return_value=_redis(f"llc:agent:{_SLUG}:paused")),
    ):
        assert await agent_ref_block_reason(session, node_pk, _COMPANY_ID) == "agent is paused"


@pytest.mark.asyncio
async def test_a_blocked_due_agent_gets_no_run_and_stays_on_the_schedule():
    scheduler = LLCHeartbeatScheduler()
    session = AsyncMock()
    context = MagicMock(
        __aenter__=AsyncMock(return_value=session),
        __aexit__=AsyncMock(return_value=False),
    )
    agent = {
        "agent_id": _SLUG,
        "heartbeat_cron": "* * * * *",
        "company_id": _COMPANY_ID,
        "status": "paused",
    }
    create_run, run_adapter, reschedule = AsyncMock(), AsyncMock(), AsyncMock()
    with (
        patch.object(scheduler, "_get_agent_config", AsyncMock(return_value=agent)),
        patch.object(scheduler, "_create_run", create_run),
        patch.object(scheduler, "_run_adapter", run_adapter),
        patch.object(scheduler, "_reschedule", reschedule),
        patch(
            f"{_HBS}.get_async_session_factory",
            return_value=MagicMock(return_value=context),
        ),
    ):
        await scheduler._handle_due_agent(_SLUG, AsyncMock())
    create_run.assert_not_called()
    run_adapter.assert_not_called()
    reschedule.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_manual_trigger_of_a_stopped_agent_raises_before_any_run():
    scheduler = LLCHeartbeatScheduler()
    agent = {"agent_id": _SLUG, "company_id": _COMPANY_ID, "status": "terminated"}
    create_run = AsyncMock()
    with (
        patch.object(scheduler, "_get_agent_config", AsyncMock(return_value=agent)),
        patch.object(scheduler, "_create_run", create_run),
        pytest.raises(AgentNotDispatchable) as raised,
    ):
        await scheduler.trigger_manual(AsyncMock(), _SLUG)
    assert raised.value.reason == "agent status is terminated"
    create_run.assert_not_called()


@pytest.mark.asyncio
async def test_require_dispatchable_passes_a_healthy_agent():
    with (
        patch(f"{_GATE}.get_async_redis_client", AsyncMock(return_value=_redis())),
        patch(f"{_GATE}.BudgetService", _budget(False)),
    ):
        await require_dispatchable(
            AsyncMock(),
            {"agent_id": _SLUG, "company_id": _COMPANY_ID, "status": "available"},
        )


def test_no_scheduler_keeps_its_own_pause_check():
    scheduler_dir = Path(__file__).resolve().parent.parent / "scheduler"
    readers = [p.name for p in scheduler_dir.glob("*.py") if ':paused"' in p.read_text(encoding="utf-8")]
    assert readers == ["dispatch_gate.py"]


class TestTriggerManual:
    @pytest.mark.asyncio
    async def test_returns_queued_run(self):
        scheduler = LLCHeartbeatScheduler()
        agent = {"agent_id": _SLUG, "company_id": _COMPANY_ID, "status": "available"}

        mock_run = MagicMock(spec=LLCHeartbeatRun)
        mock_run.id = uuid.uuid4()
        mock_run.status = LLCRunStatus.QUEUED.value

        mock_session = AsyncMock()
        mock_session.flush = AsyncMock()

        with (
            patch.object(scheduler, "_get_agent_config", new=AsyncMock(return_value=agent)),
            patch.object(scheduler, "_create_run", new=AsyncMock(return_value=mock_run)),
            patch.object(scheduler, "_run_adapter", new=AsyncMock()),
            patch(f"{_HBS}.require_dispatchable", new=AsyncMock()),
        ):
            run, agent_cfg = await scheduler.trigger_manual(mock_session, "agent-abc")

        assert run.id == mock_run.id
        assert run.status == LLCRunStatus.QUEUED.value
        assert agent_cfg == agent

    @pytest.mark.asyncio
    async def test_raises_for_unknown_agent(self):
        scheduler = LLCHeartbeatScheduler()
        mock_session = AsyncMock()

        with patch.object(scheduler, "_get_agent_config", new=AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="not found"):
                await scheduler.trigger_manual(mock_session, "agent-unknown")
