# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Integration test: paused agent wake end-to-end (GH#8733).

Verifies the full pause → queue-wakeup → resume → run-fires cycle:

1. Agent is PAUSED — _run_once is a no-op.
2. A wakeup request queued while paused stays unconsumed.
3. After resume (status → ACTIVE + scheduler.enable_agent), the next
   _run_once fires, consumes the highest-priority wakeup request, and
   writes a HeartbeatRun row whose wakeup_context matches the queued payload.
4. Multiple queued requests: only the top-priority one is consumed per tick;
   the rest stay pending for the subsequent run.

Uses in-memory SQLite with real ORM models (JSONB → JSON patch), mirroring
the pattern in test_paused_agent_wakeup_drain.py.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy.dialects.postgresql as pg
from sqlalchemy import JSON, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Stub helpers (same pattern as test_paused_agent_wakeup_drain.py)
# ---------------------------------------------------------------------------


def _make_stub(name: str, **attrs: Any) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load_models_and_scheduler():
    """Load heartbeat models and scheduler with minimal stubs, JSONB→JSON patch."""
    from pathlib import Path  # noqa: PLC0415

    backend_root = Path(__file__).parents[3] / "autobot-backend"

    _make_stub("user_management")
    _make_stub("user_management.models")

    from sqlalchemy.orm import DeclarativeBase  # noqa: PLC0415

    class _Base(DeclarativeBase):
        pass

    _make_stub("user_management.models.base", Base=_Base)

    def _now_utc():
        return datetime.now(timezone.utc)

    _make_stub("autobot_shared")
    _make_stub("autobot_shared.logging_manager", get_logger=MagicMock(return_value=MagicMock()))
    _make_stub("autobot_shared.time_utils", now_utc=_now_utc)
    _make_stub("events")
    _make_stub(
        "events.event_types",
        HEARTBEAT_RUN_COMPLETED="heartbeat_run_completed",
        HEARTBEAT_RUN_STARTED="heartbeat_run_started",
    )
    _make_stub("live_event_manager", publish_live_event=AsyncMock())
    _make_stub("events.bus", publish_event=AsyncMock())

    original_jsonb = pg.JSONB
    with patch.object(pg, "JSONB", JSON):
        hb_spec = importlib.util.spec_from_file_location("models.heartbeat", backend_root / "models" / "heartbeat.py")
        assert hb_spec and hb_spec.loader
        hb_mod = importlib.util.module_from_spec(hb_spec)
        models_pkg = types.ModuleType("models")
        sys.modules["models"] = models_pkg
        sys.modules["models.heartbeat"] = hb_mod
        hb_spec.loader.exec_module(hb_mod)  # type: ignore[union-attr]
    pg.JSONB = original_jsonb

    # Agent must be a real ORM-mapped class so select(Agent) works.
    from sqlalchemy import Column, String  # noqa: PLC0415

    class _Agent(_Base):
        __tablename__ = "agent"
        agent_id = Column(String, primary_key=True)
        agent_type = Column(String, default="worker")

    _make_stub("models.agent", Agent=_Agent)
    _make_stub("services")
    _make_stub(
        "services.run_jwt",
        get_run_jwt_scopes=MagicMock(return_value=[]),
        mint_run_jwt=MagicMock(return_value="fake-jwt"),
        revoke_run_jwt_async=AsyncMock(),
    )
    _make_stub("services.task_claim", renew_claim=AsyncMock())
    _make_stub("services.task_workspace")

    sched_spec = importlib.util.spec_from_file_location(
        "services.heartbeat_scheduler", backend_root / "services" / "heartbeat_scheduler.py"
    )
    assert sched_spec and sched_spec.loader
    sched_mod = importlib.util.module_from_spec(sched_spec)
    sys.modules["services.heartbeat_scheduler"] = sched_mod
    sched_spec.loader.exec_module(sched_mod)  # type: ignore[union-attr]

    return hb_mod, sched_mod, _Base


_hb_mod, _sched_mod, _Base = _load_models_and_scheduler()
AgentStatus = _hb_mod.AgentStatus
AgentRuntimeState = _hb_mod.AgentRuntimeState
AgentWakeupRequest = _hb_mod.AgentWakeupRequest
HeartbeatRun = _hb_mod.HeartbeatRun
WakeupTrigger = _hb_mod.WakeupTrigger
HeartbeatScheduler = _sched_mod.HeartbeatScheduler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_agent(factory: async_sessionmaker, agent_id: str, status: str) -> AgentRuntimeState:
    async with factory() as session:
        state = AgentRuntimeState(
            id=uuid.uuid4(),
            agent_id=agent_id,
            status=status,
            paused_reason="budget hard-stop" if status == AgentStatus.PAUSED.value else None,
            paused_by="system:budget" if status == AgentStatus.PAUSED.value else None,
        )
        session.add(state)
        await session.commit()
        return state


async def _set_agent_active(factory: async_sessionmaker, agent_id: str) -> None:
    """Simulate the resume_agent endpoint: clear pause fields and set ACTIVE."""
    async with factory() as session:
        result = await session.execute(select(AgentRuntimeState).where(AgentRuntimeState.agent_id == agent_id))
        state = result.scalar_one()
        state.status = AgentStatus.ACTIVE.value
        state.paused_reason = None
        state.paused_at = None
        state.paused_by = None
        await session.commit()


async def _queue_wakeup(
    factory: async_sessionmaker,
    agent_id: str,
    state_id: uuid.UUID,
    priority: int,
    context: dict,
) -> uuid.UUID:
    req_id = uuid.uuid4()
    async with factory() as session:
        req = AgentWakeupRequest(
            id=req_id,
            agent_id=agent_id,
            runtime_state_id=state_id,
            priority=priority,
            context=context,
            reason="test-wake",
        )
        session.add(req)
        await session.commit()
    return req_id


async def _run_rows(factory: async_sessionmaker, agent_id: str) -> list[HeartbeatRun]:
    async with factory() as session:
        result = await session.execute(select(HeartbeatRun).where(HeartbeatRun.agent_id == agent_id))
        return result.scalars().all()


async def _unconsumed_count(factory: async_sessionmaker, agent_id: str) -> int:
    async with factory() as session:
        result = await session.execute(
            select(AgentWakeupRequest).where(
                AgentWakeupRequest.agent_id == agent_id,
                AgentWakeupRequest.consumed_at.is_(None),
            )
        )
        return len(result.scalars().all())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPausedAgentWakeEndToEnd:
    """End-to-end: pause → queue wakeup → resume → run fires with correct context."""

    @pytest.mark.asyncio
    async def test_resume_fires_run_after_pause(self, db_factory):
        """After resuming a paused agent, _run_once creates a HeartbeatRun."""
        agent_id = str(uuid.uuid4())
        state = await _seed_agent(db_factory, agent_id, AgentStatus.PAUSED.value)
        await _queue_wakeup(db_factory, agent_id, state.id, priority=0, context={"task_id": "t1"})

        scheduler = HeartbeatScheduler(db_factory)
        scheduler._running = True

        # While paused: no run
        await scheduler._run_once(agent_id, WakeupTrigger.INTERVAL)
        assert len(await _run_rows(db_factory, agent_id)) == 0

        # Resume: transition PAUSED → ACTIVE in DB (mirrors resume_agent endpoint)
        await _set_agent_active(db_factory, agent_id)

        # After resume: run fires
        with (
            patch.object(scheduler, "_invoke_agent", AsyncMock(return_value=("completed", None, {}))),
            patch.object(scheduler, "_finalize_run", AsyncMock()),
        ):
            await scheduler._run_once(agent_id, WakeupTrigger.EVENT)

        runs = await _run_rows(db_factory, agent_id)
        assert len(runs) == 1

    @pytest.mark.asyncio
    async def test_wakeup_context_carried_into_run(self, db_factory):
        """The HeartbeatRun row carries the wakeup request's context payload."""
        agent_id = str(uuid.uuid4())
        state = await _seed_agent(db_factory, agent_id, AgentStatus.PAUSED.value)
        ctx = {"task_id": "task-abc", "reason": "blocker-resolved"}
        await _queue_wakeup(db_factory, agent_id, state.id, priority=5, context=ctx)

        await _set_agent_active(db_factory, agent_id)

        scheduler = HeartbeatScheduler(db_factory)
        scheduler._running = True

        finalized: list[dict] = []

        async def _capture_finalize(agent_id, run_id, state_id, status, error, usage, jwt):
            async with db_factory() as session:
                run = await session.get(HeartbeatRun, run_id)
                if run:
                    finalized.append(run.wakeup_context or {})

        with (
            patch.object(scheduler, "_invoke_agent", AsyncMock(return_value=("completed", None, {}))),
            patch.object(scheduler, "_finalize_run", AsyncMock(side_effect=_capture_finalize)),
        ):
            await scheduler._run_once(agent_id, WakeupTrigger.EVENT)

        assert finalized, "finalize was not called"
        assert finalized[0].get("task_id") == "task-abc"
        assert finalized[0].get("reason") == "blocker-resolved"

    @pytest.mark.asyncio
    async def test_wakeup_request_consumed_after_resume(self, db_factory):
        """The queued wakeup request is marked consumed once the run fires post-resume."""
        agent_id = str(uuid.uuid4())
        state = await _seed_agent(db_factory, agent_id, AgentStatus.PAUSED.value)
        await _queue_wakeup(db_factory, agent_id, state.id, priority=0, context={"task_id": "t2"})

        await _set_agent_active(db_factory, agent_id)

        scheduler = HeartbeatScheduler(db_factory)
        scheduler._running = True

        with (
            patch.object(scheduler, "_invoke_agent", AsyncMock(return_value=("completed", None, {}))),
            patch.object(scheduler, "_finalize_run", AsyncMock()),
        ):
            await scheduler._run_once(agent_id, WakeupTrigger.EVENT)

        assert await _unconsumed_count(db_factory, agent_id) == 0

    @pytest.mark.asyncio
    async def test_highest_priority_wakeup_consumed_first(self, db_factory):
        """With multiple queued wakeups, the highest-priority request is consumed first."""
        agent_id = str(uuid.uuid4())
        state = await _seed_agent(db_factory, agent_id, AgentStatus.PAUSED.value)
        await _queue_wakeup(db_factory, agent_id, state.id, priority=1, context={"task_id": "low"})
        await _queue_wakeup(db_factory, agent_id, state.id, priority=10, context={"task_id": "high"})
        await _queue_wakeup(db_factory, agent_id, state.id, priority=5, context={"task_id": "mid"})

        await _set_agent_active(db_factory, agent_id)

        scheduler = HeartbeatScheduler(db_factory)
        scheduler._running = True

        consumed_ctx: list[dict] = []

        async def _capture(agent_id, run_id, state_id, status, error, usage, jwt):
            async with db_factory() as session:
                run = await session.get(HeartbeatRun, run_id)
                if run and run.wakeup_context:
                    consumed_ctx.append(run.wakeup_context)

        with (
            patch.object(scheduler, "_invoke_agent", AsyncMock(return_value=("completed", None, {}))),
            patch.object(scheduler, "_finalize_run", AsyncMock(side_effect=_capture)),
        ):
            await scheduler._run_once(agent_id, WakeupTrigger.EVENT)

        assert consumed_ctx, "no wakeup context recorded"
        assert consumed_ctx[0].get("task_id") == "high"
        # Two lower-priority requests remain unconsumed
        assert await _unconsumed_count(db_factory, agent_id) == 2

    @pytest.mark.asyncio
    async def test_paused_agent_still_blocks_run_between_queue_and_resume(self, db_factory):
        """A wakeup queued while paused does not bypass the pause guard."""
        agent_id = str(uuid.uuid4())
        state = await _seed_agent(db_factory, agent_id, AgentStatus.PAUSED.value)
        await _queue_wakeup(db_factory, agent_id, state.id, priority=99, context={"task_id": "urgent"})

        scheduler = HeartbeatScheduler(db_factory)
        scheduler._running = True

        start_run_mock = AsyncMock()
        with patch.object(scheduler, "_start_run", start_run_mock):
            await scheduler._run_once(agent_id, WakeupTrigger.EVENT)

        start_run_mock.assert_not_awaited()
        # Request still unconsumed — resume hasn't happened yet
        assert await _unconsumed_count(db_factory, agent_id) == 1
