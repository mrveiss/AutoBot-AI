# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ledger's own record of coordination events nobody else keeps (#18391).

A claim that lapses, a release that addressed someone else's claim, and a yield
request are all things the registry used to forget the moment they happened:
Redis expires a claim silently, `release_scope` returns `False` and logs
nothing, and a yield request is a one-shot publish on a task channel. The read
APIs behind the agent-ledger screens need them, so they are written here --
a capped, expiring list beside the claims, in the same keyspace and Redis.

This is an *audit view*, not a second registry: nothing here grants, refuses or
orders a claim. Writing is best-effort and returns ``False`` on failure, because
the coordination fact it describes has already happened and must not fail on
its account; reading raises, so an unreachable ledger never looks empty.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from autobot_shared.coordination.claim_company import resolve_company
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp

logger = get_logger(__name__)

EVENTS_KEY = "work_claims:ledger:events"

#: Newest-first cap on retained events. A bounded audit trail, not an archive.
EVENT_CAP = env_int_clamped("AUTOBOT_LEDGER_EVENT_CAP", 500, min_v=50, max_v=5000)
#: Idle lifetime of the whole list; each write refreshes it.
EVENT_TTL_S = env_int_clamped("AUTOBOT_LEDGER_EVENT_TTL_S", 7 * 86400, min_v=3600, max_v=90 * 86400)
#: Longest free text (a yield's ``reason``) an event keeps; the ledger screens show it back to other viewers.
TEXT_CAP = env_int_clamped("AUTOBOT_LEDGER_TEXT_CAP", 280, min_v=32, max_v=2000)
#: Caller-supplied free-text fields, capped at :data:`TEXT_CAP` on write.
_FREE_TEXT_FIELDS = frozenset({"reason"})

#: A claim left the index because its TTL ran out while the holder never released it.
CLAIM_EXPIRED = "claim_expired"
#: `release_scope` was addressed at a scope another holder currently holds.
RELEASE_REFUSED = "release_refused"
YIELD_REQUESTED = "yield_requested"
YIELD_ANSWERED = "yield_answered"

#: How long a requester waits for a holder to answer before silence resolves to
#: "hold". Defined here -- not in `services/claim_yield.py`, which re-exports it --
#: because the ledger decides "unanswered" against the same number and
#: `autobot_shared` must not import from the backend.
YIELD_TIMEOUT_S = env_int_clamped("AUTOBOT_WORK_CLAIM_YIELD_TIMEOUT_S", 30, min_v=1, max_v=600)

_RESOLVE: Any = object()  # sentinel: "take the company from the ambient context"

EVENT_TYPES = frozenset({CLAIM_EXPIRED, RELEASE_REFUSED, YIELD_REQUESTED, YIELD_ANSWERED})


async def record_ledger_event(
    client: Any, event_type: str, *, company_id: str | None = _RESOLVE, **fields: Any
) -> bool:
    """Append one event. ``False`` means it was not recorded; never raises.

    *company_id* defaults to the ambient company; pass ``None`` to stamp install-wide.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown ledger event {event_type!r}; events are {sorted(EVENT_TYPES)}")
    capped = {k: v[:TEXT_CAP] if k in _FREE_TEXT_FIELDS and isinstance(v, str) else v for k, v in fields.items()}
    entry = json.dumps(
        {
            "type": event_type,
            "at": utc_timestamp(),
            "company_id": resolve_company() if company_id is _RESOLVE else company_id,
            **capped,
        }
    )
    try:
        async with client.pipeline(transaction=True) as pipe:
            pipe.lpush(EVENTS_KEY, entry)
            pipe.ltrim(EVENTS_KEY, 0, EVENT_CAP - 1)
            pipe.expire(EVENTS_KEY, EVENT_TTL_S)
            await pipe.execute()
        return True
    except Exception:  # noqa: BLE001 -- an audit write must not break the coordination it describes
        logger.warning("ledger: failed to record %s", event_type, exc_info=True)
        return False


async def record_expired_members(client: Any, kind: str, members: list[str]) -> None:
    """Record each pruned ``<path>|<agent>|<task>`` index member as an expired claim."""
    for member in members:
        path, _, rest = member.partition("|")
        agent_id, _, task_id = rest.partition("|")
        # The claim's payload is gone with its TTL, and with it the company: install-wide by default.
        await record_ledger_event(
            client, CLAIM_EXPIRED, scope=f"{kind}:{path}", agent_id=agent_id, task_id=task_id, company_id=None
        )


async def note_refused_release(
    client: Any, scope: str, agent_id: str, task_id: str, holders_of: Callable[[], Awaitable[list[Any]]]
) -> None:
    """Record a release addressed at a scope another holder currently holds.

    Called when a release removed nothing. A holder can only ever address its own
    key, so nothing was taken -- but two agents disagreeing about who owns the
    work is the condition claims exist to surface (`AGENT_COORDINATION.md`
    principle 5), and it used to leave no trace. *holders_of* returns the live
    claims; a failure there is swallowed, since observing must not raise.
    """
    try:
        held = [c for c in await holders_of() if c.scope == scope]
    except Exception:  # noqa: BLE001 -- observing a refusal must not turn it into a raise
        return
    for claim in held:
        await record_ledger_event(
            client,
            RELEASE_REFUSED,
            scope=scope,
            agent_id=agent_id,
            task_id=task_id,
            holder_agent_id=claim.agent_id,
            holder_task_id=claim.task_id,
            holder_company_id=claim.company_id,
        )


async def read_events(client: Any, limit: int | None = None) -> list[dict[str, Any]]:
    """Newest-first events. Raises on a failed read -- an empty list means none happened."""
    raw = await client.lrange(EVENTS_KEY, 0, (EVENT_CAP if limit is None else max(limit, 1)) - 1)
    return [json.loads(item.decode() if isinstance(item, bytes) else item) for item in raw]


def unanswered_yields(events: list[dict[str, Any]], *, now_epoch: float, timeout_s: float) -> list[dict[str, Any]]:
    """Yield requests with no recorded answer once *timeout_s* has passed.

    Silence means hold (`AGENT_COORDINATION.md`), so an unanswered request is a
    refusal that nobody has seen yet -- the conflict a person is likely to want
    to resolve. A request younger than the timeout is still pending, not unanswered.
    """
    answered = {e.get("token") for e in events if e["type"] == YIELD_ANSWERED}
    return [
        e
        for e in events
        if e["type"] == YIELD_REQUESTED
        and e.get("token") not in answered
        and now_epoch - datetime.fromisoformat(e["at"]).timestamp() >= timeout_s
    ]
