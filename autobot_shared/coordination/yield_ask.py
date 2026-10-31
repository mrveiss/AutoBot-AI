# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A person asks a claim's holder to release it (#18599, #18563).

The ledger's one write. It publishes a yield request on the holder's task channel
and records it -- it never releases, force-releases or deletes anything (silence
means hold; no agent cleans up on its own, #17038). The user backend and the SLM
admin router both serve it, so the lookup, the 404 rule and the rate limit live
here once; each side only binds how a message reaches the holder's channel.

Not-found is ONE answer: no such claim, held by someone else, or visible to
another company all read "404, same message", so a caller cannot probe which
scopes exist in another company.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from redis.exceptions import RedisError

from autobot_shared.coordination import ledger_read
from autobot_shared.coordination.ledger_events import YIELD_REQUESTED, cap_text
from autobot_shared.coordination.ledger_read import GENERIC_DETAIL, Company, LedgerUnreadable
from autobot_shared.coordination.work_claims import ClaimUnavailable, Scope
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.rate_limiter import RateLimiter

logger = get_logger(__name__)

#: Window over which a person may ask about one scope at most :data:`ASK_LIMIT` times.
ASK_WINDOW_S = env_int_clamped("AUTOBOT_LEDGER_YIELD_ASK_WINDOW_S", 60, min_v=1, max_v=86400)
ASK_LIMIT = env_int_clamped("AUTOBOT_LEDGER_YIELD_ASK_LIMIT", 1, min_v=1, max_v=100)

#: The one message for every kind of "not yours to ask about" -- never says which.
NOT_FOUND_DETAIL = "no such claim"
RATE_LIMITED_DETAIL = "this claim was asked about recently; wait before asking again"

#: The holder's task channel, as `a2a.task_manager` names it (a parity test pins the two together).
TASK_EVENTS_CHANNEL = "a2a:events:{}"

_limiter = RateLimiter("ledger_yield_ask")

Publish = Callable[[str, dict[str, Any]], Any]  # sync (the task manager) or async (a bare Redis client)
Record = Callable[..., Awaitable[None]]
#: `request_yield`'s shape: the user backend passes it as is, the SLM binds the publish and record it can reach.
Issue = Callable[..., Awaitable["YieldRequest"]]


@dataclass(frozen=True)
class YieldRequest:
    """A pending ask, and the token its answer will be written under."""

    token: str
    scope: str
    holder_task_id: str
    requester_agent_id: str
    requester_task_id: str
    reason: str


async def issue_yield_request(
    scope: str | Scope,
    *,
    holder_task_id: str,
    requester_agent_id: str,
    requester_task_id: str,
    reason: str,
    publish: Publish,
    record: Record,
) -> YieldRequest:
    """Publish the ask to the holder and record it, both with the reason capped (#18563)."""
    parsed = Scope.parse(scope)
    request = YieldRequest(
        token=str(uuid.uuid4()),
        scope=str(parsed),
        holder_task_id=holder_task_id,
        requester_agent_id=requester_agent_id,
        requester_task_id=requester_task_id,
        reason=cap_text(reason),
    )
    sent = publish(
        holder_task_id,
        {
            "event": "work_claim_yield_request",
            "token": request.token,
            "scope": request.scope,
            "requester_agent_id": requester_agent_id,
            "requester_task_id": requester_task_id,
            "reason": request.reason,
        },
    )
    if inspect.isawaitable(sent):
        await sent
    await record(
        YIELD_REQUESTED,
        token=request.token,
        scope=request.scope,
        holder_task_id=holder_task_id,
        requester_agent_id=requester_agent_id,
        requester_task_id=requester_task_id,
        reason=request.reason,
    )
    return request


async def _held_by(company: Company, scope: str, holder_task_id: str) -> str:
    """The canonical scope string when *holder_task_id* holds it and *company* may see it, else a 404."""
    try:
        wanted = str(Scope.parse(scope))
    except ValueError:
        raise HTTPException(status_code=404, detail=NOT_FOUND_DETAIL) from None
    # `ledger_read.claims` is the read routes' own path: the same exact-stamp `visible()` rule, and an
    # unreachable store is the typed 503 rather than a 500.
    for claim in (await ledger_read.claims(company)).claims:
        if claim.scope == wanted and claim.task_id == holder_task_id:
            return wanted
    raise HTTPException(status_code=404, detail=NOT_FOUND_DETAIL)


async def ask_holder_to_release(
    company: Company,
    *,
    user_id: str,
    scope: str,
    holder_task_id: str,
    reason: str,
    issue: Issue,
) -> str:
    """Ask on behalf of a person; returns the token. 404 before 429, so a refusal never confirms a claim exists."""
    held = await _held_by(company, scope, holder_task_id)
    if not await _limiter.acquire_window(f"{user_id}:{held}", ASK_LIMIT, ASK_WINDOW_S):
        raise HTTPException(status_code=429, detail=RATE_LIMITED_DETAIL)
    try:
        request = await issue(
            held,
            holder_task_id=holder_task_id,
            requester_agent_id=f"user:{user_id}",
            requester_task_id=f"ui:{uuid.uuid4()}",
            reason=reason,
        )
    except (ClaimUnavailable, RedisError, OSError) as exc:
        # Same typed 503 as the read routes (serve_ledger), never a 500; the cause stays in the log.
        logger.warning("agent ledger: yield request for %s not sent: %s", held, exc)
        raise LedgerUnreadable("yield", GENERIC_DETAIL) from exc
    return request.token
