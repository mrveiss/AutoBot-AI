# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Queueing behind a held scope, and who goes next (#15948).

Arbitration is pure, so it is tested directly — one case per branch, plus the
property that makes the third branch worth having at all: comparing a pair in
either order must give the same answer, or two callers reading the same two
records would both yield to each other.

The queue needs Redis, and uses `fakeredis` for the reason #15947's suite does.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio

from autobot_shared.coordination.claim_waitlist import (
    Waiter,
    arbitrate,
    depth,
    join,
    leave,
    next_waiter,
    waiters,
)
from autobot_shared.coordination.work_claims import ClaimMode, HolderError, try_acquire

try:
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover
    fakeredis_async = None


@pytest_asyncio.fixture
async def redis(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed — Redis-backed queue tests need real EVAL")
    from autobot_shared.coordination import claim_waitlist as wl_mod
    from autobot_shared.coordination import work_claims as wc_mod

    client = fakeredis_async.FakeRedis(server=fakeredis_async.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    monkeypatch.setattr(wl_mod, "get_async_redis_client", _client)
    monkeypatch.setattr(wc_mod, "get_async_redis_client", _client)
    yield client
    await client.flushall()


def _waiter(agent="a1", *, priority=0, joined="2026-09-07T10:00:00+00:00") -> Waiter:
    return Waiter(
        scope="path:a/b",
        agent_id=agent,
        task_id="t",
        mode="exclusive",
        intent="test",
        priority=priority,
        joined_at=joined,
        expires_at="2099-01-01T00:00:00+00:00",
        expires_epoch=4102444800.0,
    )


# ---------------------------------------------------------------------------
# Arbitration — pure, one case per branch
# ---------------------------------------------------------------------------


def test_higher_priority_wins():
    low, high = _waiter("a1", priority=0), _waiter("a2", priority=5)
    assert arbitrate(low, high) is high
    assert arbitrate(high, low) is high


def test_equal_priority_falls_back_to_who_waited_longer():
    early = _waiter("zz", joined="2026-09-07T10:00:00+00:00")
    late = _waiter("aa", joined="2026-09-07T11:00:00+00:00")
    assert arbitrate(early, late) is early
    assert arbitrate(late, early) is early


def test_identical_priority_and_join_time_break_on_agent_id():
    first, second = _waiter("aaa"), _waiter("bbb")
    assert arbitrate(first, second) is first
    assert arbitrate(second, first) is first


def test_arbitration_is_order_independent():
    """The property the third branch exists for.

    An unstable tiebreak means two callers comparing the same pair reach
    different answers and both yield, so the scope goes to nobody.
    """
    pairs = [
        (_waiter("a", priority=1), _waiter("b", priority=1)),
        (_waiter("a", priority=2), _waiter("b", priority=1)),
        (_waiter("a", joined="2026-09-07T09:00:00+00:00"), _waiter("b")),
    ]
    for left, right in pairs:
        assert arbitrate(left, right).agent_id == arbitrate(right, left).agent_id


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_join_returns_position_in_order(redis):
    assert await join("path:a/b", agent_id="a1", task_id="t1", intent="first") == 1
    assert await join("path:a/b", agent_id="a2", task_id="t2", intent="second") == 2
    assert await depth("path:a/b") == 2


@pytest.mark.asyncio
async def test_rejoining_refreshes_in_place_rather_than_going_to_the_back(redis):
    """A retry loop must not push an agent to the back of a queue it is in."""
    await join("path:a/b", agent_id="a1", task_id="t1", intent="first")
    await join("path:a/b", agent_id="a2", task_id="t2", intent="second")
    assert await join("path:a/b", agent_id="a1", task_id="t1", intent="first") == 1
    assert await depth("path:a/b") == 2


@pytest.mark.asyncio
async def test_leave_removes_only_that_waiter(redis):
    await join("path:a/b", agent_id="a1", task_id="t1", intent="first")
    await join("path:a/b", agent_id="a2", task_id="t2", intent="second")
    assert await leave("path:a/b", agent_id="a1", task_id="t1") is True
    remaining = await waiters("path:a/b")
    assert [w.agent_id for w in remaining] == ["a2"]
    assert await leave("path:a/b", agent_id="nobody", task_id="tx") is False


async def _expire_entry(client, scope: str, agent_id: str) -> None:
    """Age one waiter's entry out, leaving the rest of the queue alone.

    Rewrites that entry's expiry into the past in place. The earlier version of
    this test passed ``ttl_s=-1`` instead, which expired the **whole list key**
    rather than one member — so it asserted per-entry pruning while actually
    demonstrating that the queue had been deleted. It passed for the wrong
    reason, which is the failure mode this suite keeps finding elsewhere.
    """
    kind, path = scope.split(":", 1)
    key = f"work_claims:wait:{kind}:{path}"
    rows = await client.lrange(key, 0, -1)
    await client.delete(key)
    for raw in rows:
        entry = json.loads(raw)
        if entry["agent_id"] == agent_id:
            entry["expires_epoch"] = 0.0
            entry["expires_at"] = "1970-01-01T00:00:00+00:00"
        await client.rpush(key, json.dumps(entry))


@pytest.mark.asyncio
async def test_an_expired_waiter_is_skipped_not_stuck(redis):
    """A dead waiter at the head must not block the queue behind it."""
    await join("path:a/b", agent_id="a1", task_id="t1", intent="dies")
    await join("path:a/b", agent_id="a2", task_id="t2", intent="lives")
    await _expire_entry(redis, "path:a/b", "a1")

    head = await next_waiter("path:a/b")
    assert head is not None and head.agent_id == "a2"
    assert await depth("path:a/b") == 1


@pytest.mark.asyncio
async def test_a_short_lived_rejoin_does_not_evict_longer_lived_waiters(redis):
    """The key holds the whole queue, so its lifetime belongs to the queue.

    Setting the key's TTL from whichever waiter joined last let a short-lived
    joiner take the entire queue with it — including waiters whose own expiry
    was hours away.
    """
    await join("path:a/b", agent_id="a1", task_id="t1", intent="long", ttl_s=7200)
    await join("path:a/b", agent_id="a2", task_id="t2", intent="short", ttl_s=30)
    await join("path:a/b", agent_id="a2", task_id="t2", intent="short", ttl_s=30)

    ttl = await redis.ttl("work_claims:wait:path:a/b")
    assert ttl > 3600, f"key lifetime collapsed to the shortest waiter: {ttl}s"
    assert {w.agent_id for w in await waiters("path:a/b")} == {"a1", "a2"}


@pytest.mark.asyncio
async def test_concurrent_joins_all_get_a_position(redis):
    """Read-then-write lost joins under concurrency; the script must not."""
    import asyncio

    await asyncio.gather(*(join("path:a/b", agent_id=f"a{i}", task_id=f"t{i}", intent="racing") for i in range(8)))
    queued = await waiters("path:a/b")
    assert len({w.agent_id for w in queued}) == 8
    assert sorted(w.agent_id for w in queued) == [f"a{i}" for i in range(8)]


@pytest.mark.asyncio
async def test_next_waiter_is_none_on_an_empty_queue(redis):
    assert await next_waiter("path:a/b") is None


@pytest.mark.asyncio
async def test_join_validates_holder_identity(redis):
    with pytest.raises(HolderError):
        await join("path:a/b", agent_id="", task_id="t1", intent="x")


# ---------------------------------------------------------------------------
# Promotion is an invitation, not a grant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promotion_does_not_remove_the_waiter(redis):
    """The waiter drops its place by acquiring, not by being named next.

    If naming removed it, a waiter invited while the scope was still held —
    which happens whenever a second SHARED holder remains — would lose its turn
    to a notification it could not act on.
    """
    await join("path:a/b", agent_id="a1", task_id="t1", intent="waiting")
    assert (await next_waiter("path:a/b")).agent_id == "a1"
    assert await depth("path:a/b") == 1
    assert (await next_waiter("path:a/b")).agent_id == "a1"


@pytest.mark.asyncio
async def test_a_waiter_invited_while_a_shared_holder_remains_stays_queued(redis):
    """One release need not free a path, and the queue must survive that.

    This is the case a promotion that computed "can they acquire" would have to
    model separately. Promotion by retry gets it for free: the waiter tries,
    fails, and keeps its place.
    """
    await try_acquire("path:a/b", agent_id="s1", task_id="t1", mode=ClaimMode.SHARED, intent="read")
    await try_acquire("path:a/b", agent_id="s2", task_id="t2", mode=ClaimMode.SHARED, intent="read")
    await join("path:a/b", agent_id="w1", task_id="tw", intent="wants exclusive")

    from autobot_shared.coordination.work_claims import ClaimConflict, release

    await release("path:a/b", agent_id="s1", task_id="t1")
    invited = await next_waiter("path:a/b")
    assert invited is not None and invited.agent_id == "w1"

    # The invitation is honest about being an invitation: the retry still fails.
    outcome = await try_acquire("path:a/b", agent_id="w1", task_id="tw", intent="wants exclusive")
    assert isinstance(outcome, ClaimConflict)
    assert await depth("path:a/b") == 1

    # And succeeds once the last SHARED holder goes.
    await release("path:a/b", agent_id="s2", task_id="t2")
    from autobot_shared.coordination.work_claims import Claim

    assert isinstance(await try_acquire("path:a/b", agent_id="w1", task_id="tw", intent="wants exclusive"), Claim)
    assert await leave("path:a/b", agent_id="w1", task_id="tw") is True
