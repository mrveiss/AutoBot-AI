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


@pytest.mark.asyncio
async def test_missing_redis_refuses_because_a_company_pause_lives_only_there():
    with patch(f"{_GATE}.get_async_redis_client", AsyncMock(return_value=None)):
        assert await dispatch_block_reason(AsyncMock(), _SLUG, _COMPANY_ID, "available") == "pause state is unreadable"


@pytest.mark.asyncio
async def test_missing_redis_still_lets_liveness_recover_a_dead_run():
    with patch(f"{_GATE}.get_async_redis_client", AsyncMock(return_value=None)):
        assert await dispatch_block_reason(AsyncMock(), _SLUG, _COMPANY_ID, "available", deliberate_only=True) is None


@pytest.mark.asyncio
async def test_an_agent_with_no_company_is_refused_rather_than_run_unbudgeted():
    with patch(f"{_GATE}.get_async_redis_client", AsyncMock(return_value=_redis())):
        assert "no company" in await dispatch_block_reason(AsyncMock(), _SLUG, None, "available")


@pytest.mark.asyncio
async def test_a_routine_whose_assignee_is_not_in_the_company_is_refused():
    session = AsyncMock()
    session.execute.return_value = MagicMock(first=MagicMock(return_value=None))
    assert "not found" in await agent_ref_block_reason(session, uuid.uuid4(), _COMPANY_ID)


async def _due(reason=None, gate_error=None):
    """One due-agent tick; hands back the spies."""
    scheduler = LLCHeartbeatScheduler()
    session = AsyncMock()
    context = MagicMock(__aenter__=AsyncMock(return_value=session), __aexit__=AsyncMock(return_value=False))
    agent = {"agent_id": _SLUG, "heartbeat_cron": "* * * * *", "company_id": _COMPANY_ID, "status": "available"}
    create_run, reschedule = AsyncMock(), AsyncMock()
    gate = AsyncMock(return_value=reason, side_effect=gate_error)
    with (
        patch.object(scheduler, "_get_agent_config", AsyncMock(return_value=agent)),
        patch.object(scheduler, "_create_run", create_run),
        patch.object(scheduler, "_reschedule", reschedule),
        patch(f"{_HBS}.dispatch_block_reason", gate),
        patch(f"{_HBS}.get_async_session_factory", return_value=MagicMock(return_value=context)),
    ):
        await scheduler._handle_due_agent(_SLUG, AsyncMock())
    return create_run, reschedule


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["company is paused", "agent is paused", "budget is exhausted"])
async def test_the_due_path_skips_on_each_gate_reason(reason):
    create_run, reschedule = await _due(reason)
    create_run.assert_not_called()
    reschedule.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_due_path_requeues_when_the_gate_cannot_answer():
    scheduler = LLCHeartbeatScheduler()
    redis = AsyncMock()
    redis.zrangebyscore = AsyncMock(return_value=[_SLUG.encode()])
    redis.zrem = AsyncMock(return_value=1)
    with (
        patch(f"{_HBS}.get_async_redis_client", AsyncMock(return_value=redis)),
        patch.object(scheduler, "_handle_due_agent", AsyncMock(side_effect=RuntimeError("redis lost"))),
    ):
        await scheduler._dispatch_due()
    redis.zadd.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_wake_the_gate_cannot_judge_leaves_the_users_write_standing():
    from llc.models.enums import HeartbeatInvocationSource
    from llc.scheduler import event_wake

    scheduler = MagicMock(trigger_manual=AsyncMock(side_effect=RuntimeError("redis lost")))
    with (
        patch.object(event_wake, "_wakeable_slug", AsyncMock(return_value=_SLUG)),
        patch("llc.scheduler.heartbeat_scheduler.get_heartbeat_scheduler", return_value=scheduler),
    ):
        woken = await event_wake.wake_agent(
            AsyncMock(),
            company_id=_COMPANY_ID,
            agent_ref=_SLUG,
            reason=HeartbeatInvocationSource.AGENT_MENTIONED,
        )
    assert woken is None


async def _trigger(company_id, org_id):
    from fastapi import HTTPException

    from llc.api import agents

    scheduler = MagicMock(trigger_manual=AsyncMock(side_effect=AgentNotDispatchable(_SLUG, company_id, "x")))
    with (
        patch.object(agents, "get_heartbeat_scheduler", return_value=scheduler),
        pytest.raises(HTTPException) as raised,
    ):
        await agents.trigger_heartbeat(_SLUG, AsyncMock(), {}, MagicMock(org_id=org_id))
    return raised.value.status_code


@pytest.mark.asyncio
async def test_a_blocked_trigger_is_409_for_the_owner_and_404_across_tenants():
    own, other = uuid.uuid4(), uuid.uuid4()
    assert await _trigger(own, own) == 409
    assert await _trigger(other, own) == 404


@pytest.mark.asyncio
async def test_a_paused_routine_is_not_recorded_and_stays_queued():
    from llc.scheduler.routine_scheduler import RoutineScheduler

    routine = MagicMock(status="active", company_id=uuid.UUID(_COMPANY_ID), assignee_agent_id=None)
    routine.cron_schedule = "* * * * *"
    service = MagicMock(get=AsyncMock(return_value=routine), record_run=AsyncMock())
    context = MagicMock(__aenter__=AsyncMock(return_value=AsyncMock()), __aexit__=AsyncMock(return_value=False))
    requeue = AsyncMock()
    with (
        patch("user_management.database.get_async_session_factory", return_value=MagicMock(return_value=context)),
        patch("llc.services.routine_service.RoutineService", return_value=service),
        patch(f"{_GATE}.get_async_redis_client", AsyncMock(return_value=_redis(f"llc:company:{_COMPANY_ID}:paused"))),
        patch("llc.scheduler.routine_scheduler.get_async_redis_client", AsyncMock(return_value=requeue)),
    ):
        await RoutineScheduler()._dispatch_routine(str(uuid.uuid4()))
    service.record_run.assert_not_awaited()
    requeue.zadd.assert_awaited_once()
