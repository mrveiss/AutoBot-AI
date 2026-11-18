# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A manual run cancel drops a checkout's fence only while it names that checkout's holder (#16817, #19601).

The cancel used an unconditional ``DEL llc:checkout:{id}``: a fence a newer checkout had
taken -- another agent's, or a human claim's ``user:{id}`` -- was deleted from under it. It
then dropped the fence only of ``run.work_item_id``, a column nothing writes, so it dropped
none. The fence now follows the checkouts the run made (``checkout_run_id``), compared to the
value that checkout wrote.
"""

import uuid
from types import SimpleNamespace

import fakeredis
import pytest

from llc.api import runs
from llc.services import run_checkouts
from llc.tests._run_checkout_world import Item, Recorder, RoutedSession


def _run() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        agent_id="agent-a",
        invocation_source="heartbeat",
        status="running",
        work_item_id=None,
        started_at=None,
        finished_at=None,
        error=None,
        external_run_id=None,
        created_at=None,
    )


async def _cancel(monkeypatch, fence_of) -> str | None:
    """Cancel a running run whose one checkout's fence holds ``fence_of(item)``; return the fence after."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    run = _run()
    item = Item(run.company_id, run.id)
    key = f"llc:checkout:{item.id}"
    await redis.set(key, fence_of(item))

    async def client():
        return redis

    async def no_adapter(agent_id):
        return None

    monkeypatch.setattr(run_checkouts, "get_async_redis_client", client)
    monkeypatch.setattr(run_checkouts, "_activity_log", Recorder())
    monkeypatch.setattr(runs, "get_adapter_for_agent", no_adapter)
    session = RoutedSession([run], [item])
    ctx = SimpleNamespace(org_id=run.company_id)

    body = await runs.cancel_run("agent-a", str(run.id), session=session, _current_user={}, ctx=ctx)

    assert body["status"] == "cancelled" and session.commits == 1
    assert item.checkout_run_id is None
    return await redis.get(key)


@pytest.mark.asyncio
async def test_the_cancelled_runs_own_fence_is_dropped(monkeypatch):
    after = await _cancel(monkeypatch, lambda item: item.fence)
    assert after is None


@pytest.mark.asyncio
@pytest.mark.parametrize("newer", ["agent-b#another-run", "user:42"])
async def test_a_newer_holders_fence_survives_the_cancel(monkeypatch, newer):
    after = await _cancel(monkeypatch, lambda item: newer)
    assert after == newer
