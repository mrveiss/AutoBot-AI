# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ask a holder to release a scope early, and invite the next waiter (#15948).

The negotiation half of the conflict protocol. `work_claims` refuses and names
the holder; `claim_waitlist` queues the loser; this module is the conversation
between the two.

IT RIDES THE a2a TASK CHANNEL AND ADDS NO BUS. `TaskManager.publish_event`
already carries every task's state transitions to its SSE subscribers, and a
holder is identified by its ``task_id`` -- which is exactly the address this
needs. `EVENT_STATE_DOCTRINE` principle 1 says a second bus is never the answer
to a delivery problem, and it is not the answer here either.

WHY THIS LIVES IN THE BACKEND AND THE QUEUE DOES NOT. `autobot_shared` must not
import from `autobot-backend` -- nothing in that package does, and the
enforcement of that is simply that it has never happened. Publishing on the a2a
channel requires the task manager, so the notification half lands here while the
queue and the arbitration stay in `autobot_shared/coordination/claim_waitlist.py`
where they can be tested with neither a task manager nor a running backend.

SILENCE MEANS HOLD. An unanswered yield request resolves to ``hold`` when the
timeout expires. The alternative -- treating no answer as consent -- would make
a busy or crashed holder lose its scope precisely when it is least able to
object, which turns "ask nicely" into "take it after N seconds".
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from a2a.task_manager import get_task_manager
from autobot_shared.coordination.claim_waitlist import Waiter, next_waiter
from autobot_shared.coordination.work_claims import ClaimUnavailable, Scope
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

#: How long a requester waits for a holder to answer before treating it as a
#: refusal. Short: the requester is blocked while it waits, and a holder that
#: has not answered in this long is busy working -- which is itself the answer.
YIELD_TIMEOUT_S = env_int_clamped("AUTOBOT_WORK_CLAIM_YIELD_TIMEOUT_S", 30, min_v=1, max_v=600)

#: Poll interval while awaiting an answer. Redis pub/sub would avoid the poll,
#: but the decision is a single small value with a bounded wait, and a
#: subscription held open per request is more machinery than the wait deserves.
_POLL_S = 0.25

_DECISION_KEY = "work_claims:yield:{token}"

YIELD = "yield"
HOLD = "hold"


@dataclass(frozen=True)
class YieldRequest:
    """A pending ask, and the token its answer will be written under."""

    token: str
    scope: str
    holder_task_id: str
    requester_agent_id: str
    requester_task_id: str
    reason: str


async def _redis() -> Any:
    client = await get_async_redis_client(database="main")
    if client is None:
        raise ClaimUnavailable("claim_yield: Redis client unavailable; a decision cannot be recorded")
    return client


async def request_yield(
    scope: str | Scope,
    *,
    holder_task_id: str,
    requester_agent_id: str,
    requester_task_id: str,
    reason: str,
) -> YieldRequest:
    """Ask the holder of *scope* to release it early.

    Publishes on the holder's own task channel and returns immediately. The
    answer is awaited separately with :func:`await_decision`, so a caller that
    would rather queue than block can do both.
    """
    parsed = Scope.parse(scope)
    request = YieldRequest(
        token=str(uuid.uuid4()),
        scope=str(parsed),
        holder_task_id=holder_task_id,
        requester_agent_id=requester_agent_id,
        requester_task_id=requester_task_id,
        reason=reason,
    )
    get_task_manager().publish_event(
        holder_task_id,
        {
            "event": "work_claim_yield_request",
            "token": request.token,
            "scope": request.scope,
            "requester_agent_id": requester_agent_id,
            "requester_task_id": requester_task_id,
            "reason": reason,
        },
    )
    return request


async def answer_yield(token: str, decision: str, *, ttl_s: int | None = None) -> None:
    """Record the holder's answer. *decision* is :data:`YIELD` or :data:`HOLD`."""
    if decision not in (YIELD, HOLD):
        raise ValueError(f"decision must be {YIELD!r} or {HOLD!r}; got {decision!r}")
    client = await _redis()
    await client.set(
        _DECISION_KEY.format(token=token),
        decision,
        ex=YIELD_TIMEOUT_S if ttl_s is None else ttl_s,
    )


async def await_decision(request: YieldRequest, *, timeout_s: float | None = None) -> str:
    """Wait for the holder's answer, resolving to :data:`HOLD` on silence.

    Returns :data:`YIELD` only on an explicit yes. A timeout, a crashed holder
    and a holder that never subscribed are indistinguishable from here, and all
    three mean the same thing to the requester: the scope is not coming.
    """
    client = await _redis()
    key = _DECISION_KEY.format(token=request.token)
    budget = float(YIELD_TIMEOUT_S if timeout_s is None else timeout_s)
    # A monotonic deadline, not an accumulator of sleeps. Counting `_POLL_S` per
    # iteration assumes the read costs nothing, so a slow Redis overran the
    # timeout by however long its reads took -- and a timeout shorter than one
    # poll slept straight past it before checking at all. Both are bounded here:
    # the read is capped at the time remaining, and so is the sleep.
    deadline = time.monotonic() + budget
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(client.get(key), timeout=remaining)
        except asyncio.TimeoutError:
            break
        if raw is not None:
            return raw.decode() if isinstance(raw, bytes) else raw
        await asyncio.sleep(min(_POLL_S, max(0.0, deadline - time.monotonic())))
    logger.info(
        "claim_yield: %s unanswered by task %s after %ss — treating as hold",
        request.scope,
        request.holder_task_id,
        budget,
    )
    return HOLD


async def invite_next_waiter(scope: str | Scope) -> Waiter | None:
    """Tell whoever is queued behind *scope* to try again. Returns them, or None.

    Called after a release. The invitation is deliberately not a grant: the
    waiter retries `try_acquire` and may still be refused -- a path can carry
    several SHARED holders, so one release need not free it. The waiter keeps
    its place either way, and drops it only once it holds the scope.
    """
    waiter = await next_waiter(scope)
    if waiter is None:
        return None
    get_task_manager().publish_event(
        waiter.task_id,
        {
            "event": "work_claim_available",
            "scope": waiter.scope,
            "agent_id": waiter.agent_id,
            "note": "retry try_acquire; this is an invitation, not a grant",
        },
    )
    return waiter


def decode_yield_request(payload: str | dict) -> YieldRequest | None:
    """Rebuild a request from a published event, or None if it is not one.

    The holder receives these off its own task channel, where they arrive mixed
    with ordinary task events.
    """
    data = json.loads(payload) if isinstance(payload, str) else payload
    if data.get("event") != "work_claim_yield_request":
        return None
    return YieldRequest(
        token=data["token"],
        scope=data["scope"],
        holder_task_id=data.get("holder_task_id", ""),
        requester_agent_id=data["requester_agent_id"],
        requester_task_id=data["requester_task_id"],
        reason=data.get("reason", ""),
    )
