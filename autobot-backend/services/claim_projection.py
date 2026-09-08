# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""User-visible projection of who holds which work scope (#15949).

`EVENT_STATE_DOCTRINE.md` names agent-to-agent coordination *semantics* as an
anti-goal of the event layer, so none of them live here. The negotiation --
overlap, arbitration, waitlists, stewardship -- stays in
`autobot_shared/coordination/`. This module only answers the operator's
question, "who is working where", in the two forms the doctrine requires: an
event when it changes, and state that can be read back when the event was
missed.

It sits backend-side rather than beside the primitive for the same reason
`services/claim_yield.py` (#15948) does: `autobot_shared` imports nothing from
`autobot-backend`, and `events/bus.py` is backend-side. The primitive therefore
cannot publish its own events, and should not -- a claim registry that fails
when the event bus is down would be a coordination outage caused by a dashboard.

ONE PUBLISH, NOT TWO. #15949 asked for a publish to `agent:{id}` *and* a second
to `global` "so a dashboard sees the whole project". Measured on
`live_event_manager.py:126-127`, the second one is already done for us: every
publish to a non-`global` channel is delivered to that channel's subscribers
**union the `global` subscribers**. Publishing twice would therefore deliver
each event twice to every dashboard, and -- because `next_event_id` is a
per-channel Redis `INCR` -- the two copies would carry *different* event ids, so
a client could not dedupe them. `test_a_global_subscriber_sees_an_agent_scoped_claim`
pins the fan-out that makes the single publish sufficient, and
`test_the_dashboard_is_not_told_twice` pins the reason we do not add the second.

`PersistStrategy.MEMORY`, not durable replay: the recovery path for a client
that was offline is `GET /api/coordination/claims`, which reads the live table
rather than replaying history. A claim that expired while the client was away is
not something it should learn about on reconnect -- it is no longer true.
"""

from __future__ import annotations

from typing import Any

from autobot_shared.coordination.work_claims import (
    Claim,
    ClaimConflict,
    ClaimMode,
    Scope,
    list_claims,
    release,
    try_acquire,
)
from autobot_shared.logging_manager import get_logger
from events.bus import PersistStrategy, publish_event

logger = get_logger(__name__)

#: The three projected event types. Names are the wire contract; a client
#: matches on them, so they are stated once here rather than inline at each
#: publish site.
ACQUIRED = "work_claim_acquired"
RELEASED = "work_claim_released"
CONFLICT = "work_claim_conflict"


def _channel(agent_id: str) -> str:
    """The agent's own channel. `global` subscribers receive it too -- see the
    module docstring; that fan-out is why nothing here publishes twice."""
    return f"agent:{agent_id}"


def claim_payload(claim: Claim) -> dict[str, Any]:
    """The wire shape of a held scope.

    Every field is already user-facing. Scope paths are repo-relative by
    construction -- `Scope.parse` rejects an empty leading segment, so an
    absolute path like `/opt/autobot/x` cannot become a scope in the first
    place, and no internal filesystem path can reach a payload through here.
    """
    return {
        "scope": claim.scope,
        "kind": claim.parsed_scope.kind,
        "agent_id": claim.agent_id,
        "task_id": claim.task_id,
        "mode": claim.mode,
        "intent": claim.intent,
        "acquired_at": claim.acquired_at,
        "expires_at": claim.expires_at,
    }


async def publish_acquired(claim: Claim) -> None:
    """Announce a newly held scope on its holder's channel."""
    await publish_event(_channel(claim.agent_id), ACQUIRED, claim_payload(claim), persist=PersistStrategy.MEMORY)


async def publish_released(scope: str, *, agent_id: str, task_id: str) -> None:
    """Announce that a scope is free again.

    Takes the identifiers rather than a `Claim` because release happens *after*
    the record is gone -- there is no claim left to describe.
    """
    payload = {"scope": str(Scope.parse(scope)), "agent_id": agent_id, "task_id": task_id}
    await publish_event(_channel(agent_id), RELEASED, payload, persist=PersistStrategy.MEMORY)


async def publish_conflict(conflict: ClaimConflict, *, agent_id: str, task_id: str) -> None:
    """Announce a refusal on the **requester's** channel, not the holder's.

    The requester is the one who has to do something about it -- wait, ask, or
    pick different work. The holder is already working and needs no interruption
    from a request it never saw.
    """
    payload = {
        "requested": conflict.requested,
        "agent_id": agent_id,
        "task_id": task_id,
        "holder": claim_payload(conflict.holder),
        "reason": str(conflict),
    }
    await publish_event(_channel(agent_id), CONFLICT, payload, persist=PersistStrategy.MEMORY)


async def acquire_and_publish(
    scope: str | Scope, *, agent_id: str, task_id: str, mode: ClaimMode = ClaimMode.EXCLUSIVE, intent: str
) -> Claim | ClaimConflict:
    """Acquire *scope* and project the outcome. The entry point #15950 should use.

    The publish is deliberately not the caller's second step. Enforcement adds
    an acquire at every declared write site, and a projection that each of those
    sites must remember to call separately is one that will be missing from some
    of them -- the events would then describe a subset of the fleet, which is
    worse than none, because the gaps are invisible.

    A failed publish never fails the claim. The claim is the coordination fact;
    the event is a view of it. Losing the dashboard must not stop the work, so
    this returns the outcome either way and records the failure.
    """
    outcome = await try_acquire(scope, agent_id=agent_id, task_id=task_id, mode=mode, intent=intent)
    try:
        if isinstance(outcome, Claim):
            await publish_acquired(outcome)
        else:
            await publish_conflict(outcome, agent_id=agent_id, task_id=task_id)
    except Exception:  # noqa: BLE001 -- a dashboard must not break coordination
        logger.exception("claim projection failed for %s; the claim itself is unaffected", scope)
    return outcome


async def release_and_publish(scope: str | Scope, *, agent_id: str, task_id: str) -> bool:
    """Release *scope* and project it. Same failure rule as :func:`acquire_and_publish`."""
    released = await release(scope, agent_id=agent_id, task_id=task_id)
    if released:
        try:
            await publish_released(str(Scope.parse(scope)), agent_id=agent_id, task_id=task_id)
        except Exception:  # noqa: BLE001 -- see above
            logger.exception("claim release projection failed for %s", scope)
    return released


def _covered_by(prefix: Scope, scope: Scope) -> bool:
    """True when *prefix* covers *scope*, segment-aligned.

    Deliberately not `str.startswith`: that would report `path:a/bc` as under
    `path:a/b`, which is the exact mismatch `Scope.overlaps` exists to avoid.
    A filter that disagrees with the claim rule would show an operator a table
    that does not match what the registry actually enforces.
    """
    return prefix.kind == scope.kind and (prefix.path == scope.path or scope.path.startswith(f"{prefix.path}/"))


async def claim_table(
    *, agent_id: str | None = None, scope_prefix: str | None = None, kind: str | None = None
) -> list[dict[str, Any]]:
    """The live claim table, newest expiry last, filtered as asked.

    This is the doctrine's "state over notification" half: a client that was
    disconnected during an acquire reads the same holdings here that the event
    would have told it.
    """
    claims = await list_claims(kind)
    if agent_id is not None:
        claims = [c for c in claims if c.agent_id == agent_id]
    if scope_prefix is not None:
        prefix = Scope.parse(scope_prefix)
        claims = [c for c in claims if _covered_by(prefix, c.parsed_scope)]
    return [claim_payload(c) for c in sorted(claims, key=lambda c: (c.expires_at, c.scope))]
