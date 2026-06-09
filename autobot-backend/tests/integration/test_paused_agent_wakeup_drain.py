# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Integration test: paused agent wakeup queue drain (GH#6476 AC-9).

Verifies that when an agent is paused:
- _run_once() returns without creating a HeartbeatRun
- Queued wakeup requests remain unconsumed after _run_once
- Both interval and event triggers are blocked

Uses an in-memory SQLite engine with real ORM models.  SQLite does not
support JSONB, so the fixture patches JSONB → JSON before table creation.
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
# Stub helpers (mirrors test_agent_status.py / test_heartbeat_coalescing.py)
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

    # --- Stubs ---
    _make_stub("user_management")
    _make_stub("user_management.models")

    # Real declarative base so models get __table__ / metadata.
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

    # Patch JSONB → JSON so SQLite can create these tables.
    original_jsonb = pg.JSONB

    with patch.object(pg, "JSONB", JSON):
        hb_spec = importlib.util.spec_from_file_location("models.heartbeat", backend_root / "models" / "heartbeat.py")
        assert hb_spec and hb_spec.loader
        hb_mod = importlib.util.module_from_spec(hb_spec)
        models_pkg = types.ModuleType("models")
        sys.modules["models"] = models_pkg
        sys.modules["models.heartbeat"] = hb_mod
        hb_spec.loader.exec_module(hb_mod)  # type: ignore[union-attr]

    pg.JSONB = original_jsonb  # restore

    _make_stub("models.agent", Agent=MagicMock())
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
    """In-memory SQLite DB with heartbeat ORM tables (JSONB replaced with JSON)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_paused_agent(factory: async_sessionmaker, agent_id: str) -> AgentRuntimeState:
    async with factory() as session:
        state = AgentRuntimeState(
            id=uuid.uuid4(),
            agent_id=agent_id,
            status=AgentStatus.PAUSED.value,
            paused_reason="budget hard-stop",
            paused_by="system:budget",
        )
        session.add(state)
        await session.commit()
        return state


async def _seed_active_agent(factory: async_sessionmaker, agent_id: str) -> AgentRuntimeState:
    async with factory() as session:
        state = AgentRuntimeState(
            id=uuid.uuid4(),
            agent_id=agent_id,
            status=AgentStatus.ACTIVE.value,
        )
        session.add(state)
        await session.commit()
        return state


async def _seed_wakeup_requests(factory: async_sessionmaker, agent_id: str, state_id: uuid.UUID, count: int) -> None:
    async with factory() as session:
        for i in range(count):
            req = AgentWakeupRequest(
                id=uuid.uuid4(),
                agent_id=agent_id,
                runtime_state_id=state_id,
                priority=i,
                context={"task_id": f"task-{i}"},
                reason=f"test-wakeup-{i}",
            )
            session.add(req)
        await session.commit()


async def _unconsumed_count(factory: async_sessionmaker, agent_id: str) -> int:
    async with factory() as session:
        result = await session.execute(
            select(AgentWakeupRequest).where(
                AgentWakeupRequest.agent_id == agent_id,
                AgentWakeupRequest.consumed_at.is_(None),
            )
        )
        return len(result.scalars().all())


async def _run_count(factory: async_sessionmaker, agent_id: str) -> int:
    async with factory() as session:
        result = await session.execute(select(HeartbeatRun).where(HeartbeatRun.agent_id == agent_id))
        return len(result.scalars().all())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPausedAgentWakeupQueueDrain:
    """Integration: paused agent — no runs fire and queue stays intact."""

    @pytest.mark.asyncio
    async def test_run_once_skips_paused_agent(self, db_factory):
        """_run_once returns immediately; _start_run is never called."""
        agent_id = str(uuid.uuid4())
        await _seed_paused_agent(db_factory, agent_id)

        scheduler = HeartbeatScheduler(db_factory)
        scheduler._running = True

        start_run_mock = AsyncMock()
        with patch.object(scheduler, "_start_run", start_run_mock):
            await scheduler._run_once(agent_id, WakeupTrigger.INTERVAL)

        start_run_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_heartbeat_run_row_created_while_paused(self, db_factory):
        """No HeartbeatRun row is written to the DB when the agent is paused."""
        agent_id = str(uuid.uuid4())
        await _seed_paused_agent(db_factory, agent_id)

        scheduler = HeartbeatScheduler(db_factory)
        scheduler._running = True

        await scheduler._run_once(agent_id, WakeupTrigger.INTERVAL)

        assert await _run_count(db_factory, agent_id) == 0

    @pytest.mark.asyncio
    async def test_wakeup_queue_not_drained_while_paused(self, db_factory):
        """Queued wakeup requests remain unconsumed after _run_once on paused agent."""
        agent_id = str(uuid.uuid4())
        state = await _seed_paused_agent(db_factory, agent_id)
        await _seed_wakeup_requests(db_factory, agent_id, state.id, count=3)

        scheduler = HeartbeatScheduler(db_factory)
        scheduler._running = True

        await scheduler._run_once(agent_id, WakeupTrigger.INTERVAL)

        assert await _unconsumed_count(db_factory, agent_id) == 3

    @pytest.mark.asyncio
    async def test_event_trigger_also_skipped_while_paused(self, db_factory):
        """Event-triggered _run_once skips a paused agent too."""
        agent_id = str(uuid.uuid4())
        state = await _seed_paused_agent(db_factory, agent_id)
        await _seed_wakeup_requests(db_factory, agent_id, state.id, count=2)

        scheduler = HeartbeatScheduler(db_factory)
        scheduler._running = True

        await scheduler._run_once(agent_id, WakeupTrigger.EVENT)

        assert await _unconsumed_count(db_factory, agent_id) == 2

    @pytest.mark.asyncio
    async def test_active_agent_does_not_skip(self, db_factory):
        """Sanity: _start_run IS called for an active agent (not skipped like paused)."""
        agent_id = str(uuid.uuid4())
        await _seed_active_agent(db_factory, agent_id)

        scheduler = HeartbeatScheduler(db_factory)
        scheduler._running = True

        fake_run_id = uuid.uuid4()
        fake_state_id = uuid.uuid4()
        start_run_mock = AsyncMock(return_value=(fake_run_id, fake_state_id, 60, "fake-jwt", None))
        with (
            patch.object(scheduler, "_start_run", start_run_mock),
            patch.object(scheduler, "_invoke_agent", AsyncMock(return_value=("completed", None, {}))),
            patch.object(scheduler, "_finalize_run", AsyncMock()),
        ):
            await scheduler._run_once(agent_id, WakeupTrigger.INTERVAL)

        # For an active agent, _start_run must have been called.
        start_run_mock.assert_awaited_once()
