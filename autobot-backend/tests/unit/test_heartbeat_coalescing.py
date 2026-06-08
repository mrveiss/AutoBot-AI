# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Unit tests for heartbeat wakeup coalescing (#6472).

Verifies that HeartbeatScheduler.wakeup() deduplicates by (agent_id, task_id)
for un-consumed requests: multiple calls for the same task_id produce exactly
one row, with merged context, max priority, and incremented merged_count.

Uses importlib to load only the scheduler module (not the whole services
package), plus lightweight stubs for ORM/infrastructure deps.

The sqlalchemy `select` call is patched to a chainable MagicMock so the
query-builder code doesn't need a real mapped class — only session.execute()
is inspected by the tests.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stubs + direct-file module loading
# ---------------------------------------------------------------------------


def _make_stub(name: str, **attrs: Any) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load_scheduler() -> types.ModuleType:
    """Load heartbeat_scheduler.py directly, bypassing services/__init__.py."""
    # Fake ORM base so models.heartbeat loads without the full user_management chain
    _make_stub("user_management")
    _make_stub("user_management.models")
    _make_stub("user_management.models.base", Base=type("Base", (), {}))

    # Minimal autobot_shared stubs
    _make_stub("autobot_shared")
    _make_stub("autobot_shared.logging_manager", get_logger=MagicMock(return_value=MagicMock()))
    _make_stub("autobot_shared.time_utils", now_utc=MagicMock())

    # events / live event manager
    _make_stub("events")
    _make_stub(
        "events.event_types",
        HEARTBEAT_RUN_COMPLETED="heartbeat_run_completed",
        HEARTBEAT_RUN_STARTED="heartbeat_run_started",
    )
    _make_stub("live_event_manager", publish_live_event=AsyncMock())

    # models.heartbeat — loaded directly so Column/JSONB work; we swap Base
    backend_root = Path(__file__).parents[3] / "autobot-backend"
    hb_spec = importlib.util.spec_from_file_location("models.heartbeat", backend_root / "models" / "heartbeat.py")
    assert hb_spec and hb_spec.loader
    hb_mod = importlib.util.module_from_spec(hb_spec)
    sys.modules["models"] = types.ModuleType("models")
    sys.modules["models.heartbeat"] = hb_mod
    hb_spec.loader.exec_module(hb_mod)  # type: ignore[union-attr]

    # models.agent
    _make_stub("models.agent", Agent=MagicMock())

    # services.run_jwt
    _make_stub("services")
    _make_stub(
        "services.run_jwt",
        get_run_jwt_scopes=MagicMock(),
        mint_run_jwt=AsyncMock(),
        revoke_run_jwt_async=AsyncMock(),
    )

    # Load the scheduler
    sched_spec = importlib.util.spec_from_file_location(
        "services.heartbeat_scheduler", backend_root / "services" / "heartbeat_scheduler.py"
    )
    assert sched_spec and sched_spec.loader
    sched_mod = importlib.util.module_from_spec(sched_spec)
    sys.modules["services.heartbeat_scheduler"] = sched_mod
    sched_spec.loader.exec_module(sched_mod)  # type: ignore[union-attr]
    return sched_mod


_mod = _load_scheduler()
HeartbeatScheduler = _mod.HeartbeatScheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_req(agent_id: str, task_id: str, priority: int = 0, merged: int = 0) -> MagicMock:
    req = MagicMock()
    req.id = uuid.uuid4()
    req.agent_id = agent_id
    req.context = {"task_id": task_id}
    req.priority = priority
    req.merged_count = merged
    req.consumed_at = None
    return req


def _make_state(agent_id: str) -> MagicMock:
    state = MagicMock()
    state.id = uuid.uuid4()
    state.agent_id = agent_id
    return state


def _session_returning(scalar: Any) -> AsyncMock:
    """Async session whose execute().scalar_one_or_none() returns `scalar`."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _chainable_select() -> MagicMock:
    """Return a MagicMock that returns itself on every attribute/call chain."""
    m = MagicMock()
    m.where.return_value = m
    m.with_for_update.return_value = m
    m.limit.return_value = m
    m.__getitem__.return_value = m
    return m


# ---------------------------------------------------------------------------
# Tests
# Patch `select` in the scheduler module so query-builder code doesn't
# attempt to use the real SQLAlchemy mapped class metadata.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_coalescing_without_task_id() -> None:
    """Wakeup without task_id in context always inserts a new row."""
    scheduler = HeartbeatScheduler.__new__(HeartbeatScheduler)
    scheduler._running = False
    scheduler._tasks = {}
    state = _make_state("agent-1")
    inserted: list[Any] = []

    def make_session() -> AsyncMock:
        s = _session_returning(None)
        s.add = lambda row: inserted.append(row)
        return s

    scheduler._session_factory = MagicMock(side_effect=make_session)
    fake_req = MagicMock()
    fake_req.id = uuid.uuid4()

    with (
        patch.object(_mod, "select", return_value=_chainable_select()),
        patch.object(_mod, "AgentWakeupRequest", return_value=fake_req),
        patch.object(_mod, "_get_or_create_state", AsyncMock(return_value=state)),
    ):
        id1 = await scheduler.wakeup("agent-1", context={"foo": "bar"}, priority=1)
        fake_req.id = uuid.uuid4()  # different id for second call
        id2 = await scheduler.wakeup("agent-1", context={"foo": "baz"}, priority=2)

    assert id1 != id2
    assert len(inserted) == 2


@pytest.mark.asyncio
async def test_coalesce_on_same_task_id() -> None:
    """Five wakeups for same task_id → 1 row inserted, merged_count=4."""
    scheduler = HeartbeatScheduler.__new__(HeartbeatScheduler)
    scheduler._running = False
    scheduler._tasks = {}

    agent_id = "agent-coalesce"
    task_id = "task-abc"
    existing_req = _make_req(agent_id, task_id, priority=0, merged=0)
    state = _make_state(agent_id)
    inserted: list[Any] = []
    call_num = [0]

    def make_session() -> AsyncMock:
        call_num[0] += 1
        if call_num[0] == 1:
            s = _session_returning(None)
            s.add = lambda row: inserted.append(row)
            return s
        return _session_returning(existing_req)

    scheduler._session_factory = MagicMock(side_effect=make_session)
    new_row = MagicMock()
    new_row.id = uuid.uuid4()

    with (
        patch.object(_mod, "select", return_value=_chainable_select()),
        patch.object(_mod, "AgentWakeupRequest", return_value=new_row),
        patch.object(_mod, "_get_or_create_state", AsyncMock(return_value=state)),
    ):
        await scheduler.wakeup(agent_id, context={"task_id": task_id}, priority=0)
        for i in range(4):
            ret_id = await scheduler.wakeup(agent_id, context={"task_id": task_id}, priority=i)
            assert ret_id == str(existing_req.id)

    assert len(inserted) == 1
    assert existing_req.merged_count == 4


@pytest.mark.asyncio
async def test_coalesce_takes_max_priority() -> None:
    """Coalescing takes the max priority across all wakeups."""
    scheduler = HeartbeatScheduler.__new__(HeartbeatScheduler)
    scheduler._running = False
    scheduler._tasks = {}

    existing_req = _make_req("agent-p", "task-p", priority=3, merged=0)
    scheduler._session_factory = MagicMock(return_value=_session_returning(existing_req))

    with (
        patch.object(_mod, "select", return_value=_chainable_select()),
        patch.object(_mod, "_get_or_create_state", AsyncMock()),
    ):
        await scheduler.wakeup("agent-p", context={"task_id": "task-p"}, priority=10)

    assert existing_req.priority == 10


@pytest.mark.asyncio
async def test_coalesce_merges_context() -> None:
    """Coalescing merges context dicts; incoming keys win on conflict."""
    scheduler = HeartbeatScheduler.__new__(HeartbeatScheduler)
    scheduler._running = False
    scheduler._tasks = {}

    existing_req = _make_req("agent-c", "task-c")
    existing_req.context = {"task_id": "task-c", "a": "old", "b": "keep"}
    scheduler._session_factory = MagicMock(return_value=_session_returning(existing_req))

    with (
        patch.object(_mod, "select", return_value=_chainable_select()),
        patch.object(_mod, "_get_or_create_state", AsyncMock()),
    ):
        await scheduler.wakeup("agent-c", context={"task_id": "task-c", "a": "new", "c": "added"}, priority=0)

    assert existing_req.context["a"] == "new"
    assert existing_req.context["b"] == "keep"
    assert existing_req.context["c"] == "added"
