# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Queue behind a held scope, and decide who goes next (#15948).

`work_claims` (#15947) answers "may I have this scope" and, on a refusal, names
the holder so the loser can act. This module is what the loser does next: it
queues, and when the scope frees it is told to try again.

PROMOTION IS AN INVITATION, NOT A GRANT, and that is the load-bearing decision
here. Nothing in this module computes whether a waiter *could* acquire -- it
names who is next and lets them call
:func:`~autobot_shared.coordination.work_claims.try_acquire` themselves.

The alternative was to evaluate "does anything still overlap this waiter's scope
in a conflicting mode" at promotion time. That predicate already exists twice --
once as :meth:`Scope.overlaps` and once inside the acquire Lua -- and #15947
needed an exhaustive test over 6084 ordered pairs to stop those two drifting
apart. A third copy would need pinning to both. Promotion by retry reuses the
predicate by *using* it, so there is nothing to keep in sync.

That also makes the multi-holder case correct for free. A path can carry several
SHARED claims, so releasing one holder does not free the path; a waiter promoted
on "the holder released" would be woken to a scope still held. A waiter that
retries simply fails and stays queued.

WHO NOTIFIES. This module provides the queue and the query. It does not send the
notification, because notifying a waiting agent means publishing on the a2a task
channel, and `autobot_shared` must not import from `autobot-backend` -- nothing
in this package does. The backend service that owns the release path calls
:func:`next_waiter` and publishes. Splitting it that way keeps the layering
intact and keeps this module testable without a task manager.

FAIRNESS IS FIFO, THEN ARBITRATED. Position is join order. :func:`arbitrate` is
consulted only when two contenders must be compared directly -- a total,
deterministic function with no I/O, so the reason one agent went first is
reconstructible from the two records alone rather than from a Redis state
nobody kept.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any

from autobot_shared.coordination.work_claims import (
    ClaimMode,
    ClaimUnavailable,
    Scope,
    _require_holder,
)
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)

#: How long a waiter keeps its place without renewing. Longer than a claim's TTL
#: on purpose: a waiter that expires before the holder it is waiting for would
#: never be promoted, and would look to an operator like a queue that silently
#: drops people.
WAIT_TTL_S = env_int_clamped("AUTOBOT_WORK_CLAIM_WAIT_TTL_S", 900, min_v=30, max_v=7200)

_WAIT_KEY = "work_claims:wait:{kind}:{path}"


@dataclass(frozen=True)
class Waiter:
    """One agent queued behind a scope it was refused."""

    scope: str
    agent_id: str
    task_id: str
    mode: str
    intent: str
    priority: int
    joined_at: str
    expires_at: str

    def is_expired(self, now_iso: str) -> bool:
        return self.expires_at <= now_iso


def arbitrate(first: Waiter, second: Waiter) -> Waiter:
    """Which of two contenders takes the scope. Pure, total, deterministic.

    Three rules, in order, and the third exists so the answer never depends on
    which order the two were read out of Redis:

    1. Higher ``priority`` wins -- the only rule an operator sets deliberately.
    2. Earlier ``joined_at`` wins -- waiting longer is the tiebreak that keeps a
       queue a queue.
    3. Lower ``agent_id`` wins -- arbitrary, and that is the point: an arbitrary
       *stable* rule beats a fair *unstable* one, because two callers comparing
       the same pair must reach the same answer or they will both yield.
    """
    if first.priority != second.priority:
        return first if first.priority > second.priority else second
    if first.joined_at != second.joined_at:
        return first if first.joined_at < second.joined_at else second
    return first if first.agent_id <= second.agent_id else second


async def _redis() -> Any:
    client = await get_async_redis_client(database="main")
    if client is None:
        raise ClaimUnavailable("claim_waitlist: Redis client unavailable; the queue cannot be trusted")
    return client


def _key(scope: Scope) -> str:
    return _WAIT_KEY.format(kind=scope.kind, path=scope.path)


def _decode(raw: bytes | str) -> Waiter:
    if isinstance(raw, bytes):
        raw = raw.decode()
    return Waiter(**json.loads(raw))


async def join(
    scope: str | Scope,
    *,
    agent_id: str,
    task_id: str,
    mode: ClaimMode = ClaimMode.EXCLUSIVE,
    intent: str,
    priority: int = 0,
    ttl_s: int | None = None,
) -> int:
    """Queue behind *scope*. Returns this waiter's 1-based position.

    Re-joining as the same ``(agent_id, task_id)`` moves nobody: the existing
    entry is refreshed in place, so a retry loop cannot push an agent to the
    back of a queue it is already in.
    """
    parsed = Scope.parse(scope)
    _require_holder(agent_id, task_id)
    ttl = WAIT_TTL_S if ttl_s is None else ttl_s
    joined = now_utc()
    client = await _redis()
    key = _key(parsed)

    existing = await waiters(parsed)
    for position, waiter in enumerate(existing, start=1):
        if waiter.agent_id == agent_id and waiter.task_id == task_id:
            refreshed = Waiter(
                **{**asdict(waiter), "expires_at": (joined + timedelta(seconds=ttl)).isoformat()}
            )
            await client.lset(key, position - 1, json.dumps(asdict(refreshed)))
            await client.expire(key, ttl)
            return position

    entry = Waiter(
        scope=str(parsed),
        agent_id=agent_id,
        task_id=task_id,
        mode=mode.value if isinstance(mode, ClaimMode) else str(mode),
        intent=intent,
        priority=priority,
        joined_at=joined.isoformat(),
        expires_at=(joined + timedelta(seconds=ttl)).isoformat(),
    )
    await client.rpush(key, json.dumps(asdict(entry)))
    await client.expire(key, ttl)
    return len(existing) + 1


async def leave(scope: str | Scope, *, agent_id: str, task_id: str) -> bool:
    """Drop this waiter's place. True when one was removed.

    Called by a waiter that acquired the scope, and by one that gave up. A
    waiter that simply dies is removed by expiry instead.
    """
    parsed = Scope.parse(scope)
    _require_holder(agent_id, task_id)
    client = await _redis()
    key = _key(parsed)
    for raw in await client.lrange(key, 0, -1):
        waiter = _decode(raw)
        if waiter.agent_id == agent_id and waiter.task_id == task_id:
            await client.lrem(key, 1, raw if isinstance(raw, str) else raw.decode())
            return True
    return False


async def waiters(scope: str | Scope) -> list[Waiter]:
    """Everyone queued behind *scope*, in position order, expired entries dropped.

    Pruning happens on read for the same reason it does in ``list_claims``:
    Redis expires the list as a whole, not its elements, so a queue that outlives
    one of its members is tidied by whoever looks next.
    """
    parsed = Scope.parse(scope)
    client = await _redis()
    key = _key(parsed)
    now_iso = now_utc().isoformat()
    live: list[Waiter] = []
    for raw in await client.lrange(key, 0, -1):
        waiter = _decode(raw)
        if waiter.is_expired(now_iso):
            await client.lrem(key, 1, raw if isinstance(raw, str) else raw.decode())
            continue
        live.append(waiter)
    return live


async def next_waiter(scope: str | Scope) -> Waiter | None:
    """Who should be invited to retry *scope*, or None if nobody is queued.

    **Does not remove the waiter and does not grant anything.** The invitation
    is to call ``try_acquire``; the waiter drops its place with :func:`leave`
    once it actually holds the scope. A waiter that is invited and still refused
    -- because a second SHARED holder remains, or because it lost a race -- keeps
    its position rather than losing its turn to a notification.
    """
    queued = await waiters(scope)
    return queued[0] if queued else None


async def depth(scope: str | Scope) -> int:
    """How many live waiters are queued behind *scope*."""
    return len(await waiters(scope))
