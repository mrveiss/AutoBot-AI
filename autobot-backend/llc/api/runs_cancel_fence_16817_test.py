# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A manual run cancel drops the checkout fence only while the run's agent holds it (#16817).

The cancel used an unconditional ``DEL llc:checkout:{id}``: a fence a newer checkout had
taken -- another agent's, or a human claim's ``user:{id}`` -- was deleted from under it.
"""

import uuid
from types import SimpleNamespace

import fakeredis
import pytest

from llc.api import runs
from testkit.fake_async_session import FakeAsyncSession, FakeResult


def _run(agent_id: str, work_item_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        agent_id=agent_id,
        invocation_source="heartbeat",
        status="running",
        work_item_id=work_item_id,
        started_at=None,
        finished_at=None,
        error=None,
        external_run_id=None,
        created_at=None,
    )


async def _cancel(monkeypatch, fence_value: str) -> str | None:
    """Cancel a running run whose item's fence holds *fence_value*; return the fence after."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    item_id = uuid.uuid4()
    run = _run("agent-a", item_id)
    await redis.set(f"llc:checkout:{item_id}", fence_value)

    async def client():
        return redis

    async def no_adapter(agent_id):
        return None

    monkeypatch.setattr(runs, "get_async_redis_client", client)
    monkeypatch.setattr(runs, "get_adapter_for_agent", no_adapter)
    session = FakeAsyncSession(results=[FakeResult([run])])
    ctx = SimpleNamespace(org_id=run.company_id)

    body = await runs.cancel_run("agent-a", str(run.id), session=session, _current_user={}, ctx=ctx)

    assert body["status"] == "cancelled" and session.commits == 1
    return await redis.get(f"llc:checkout:{item_id}")


@pytest.mark.asyncio
async def test_the_cancelled_runs_own_fence_is_dropped(monkeypatch):
    assert await _cancel(monkeypatch, "agent-a") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("newer", ["agent-b", "user:42"])
async def test_a_newer_holders_fence_survives_the_cancel(monkeypatch, newer):
    assert await _cancel(monkeypatch, newer) == newer
