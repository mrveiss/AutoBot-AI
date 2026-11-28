# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read-only views over the coordination stores, shared by both ledger APIs (#18391).

The user backend (scoped to one company) and the SLM backend (install-wide,
admin only) read the same Redis, so the reading lives here once and the two
routers only decide *whose* rows they may show. Nothing in this module writes,
releases, deletes or reorders anything -- the stores' own modules stay the only
way to change a claim.

**Unreadable is not empty.** Every function here raises :class:`LedgerUnreadable`
when its store cannot be read, naming the source. A router turns that into
HTTP 503; an empty result therefore always means the store was read and held
nothing (`MEASUREMENT_DISCIPLINE.md`: *nothing found* versus *did not look*).

**Company scoping is by the company stamped at write time** (`claim_company.py`), never by
the agent's name. A company sees only records stamped with its id; an unstamped record
(install-wide actor, or written before stamping) is visible only to the install-wide view
(``company=None``). Fail closed.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, TypeVar

from redis.exceptions import RedisError

from autobot_shared.coordination import dev_loop_actions
from autobot_shared.coordination.claim_waitlist import Waiter, all_waiters
from autobot_shared.coordination.ledger_events import (
    CLAIM_EXPIRED,
    EVENT_CAP,
    RELEASE_REFUSED,
    YIELD_TIMEOUT_S,
    read_events,
    unanswered_yields,
)
from autobot_shared.coordination.ledger_schemas import (
    ActivityResponse,
    ActivityRow,
    ClaimRow,
    ClaimsResponse,
    ConflictRow,
    ConflictsResponse,
    ContentionResponse,
    ContentionRow,
    DevLoopActionRow,
    DevLoopHistoryResponse,
    DevLoopIssuesResponse,
    WaiterRow,
    WaitlistsResponse,
)
from autobot_shared.coordination.work_claims import ClaimUnavailable, WorkClaim, claim_payload, list_claims
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

GENERIC_DETAIL = "the coordination store could not be read"

T = TypeVar("T")

#: Shared, contended resources (#16951): the scope kinds the SLM contention view shows.
RESOURCE_KINDS = ("provider", "cpu", "queue")

SOURCE_CLAIMS = "claims"
SOURCE_WAITLISTS = "waitlists"
SOURCE_EVENTS = "events"
SOURCE_DEV_LOOP = "dev_loop"

#: ``None`` = the install-wide view (SLM, admin): every record, stamped or not. A string = that
#: company: only records STAMPED with it at write time (`claim_company.py`).
Company = str | None


class LedgerUnreadable(Exception):
    """A coordination store could not be read -- distinct from the store being empty."""

    def __init__(self, source: str, detail: str) -> None:
        super().__init__(f"{source}: {detail}")
        self.source = source
        self.detail = detail


async def _read(source: str, call: Callable[[], Awaitable[T]]) -> T:
    """Run *call*, turning every 'cannot reach Redis' shape into :class:`LedgerUnreadable`."""
    try:
        return await call()
    except (ClaimUnavailable, RedisError, OSError) as exc:
        # The cause (which may name a Redis host and port) stays in the server log; the caller gets a generic reason.
        logger.warning("agent ledger: %s could not be read: %s", source, exc)
        raise LedgerUnreadable(source, GENERIC_DETAIL) from exc


def _dev_loop(call: Callable[[], Awaitable[T]]) -> Callable[[], Awaitable[T]]:
    """``dev_loop_actions`` signals an unreadable Redis with ``RuntimeError``; say so only for that source."""

    async def _run() -> T:
        try:
            return await call()
        except RuntimeError as exc:
            raise ClaimUnavailable(f"dev loop store unreadable: {exc}") from exc

    return _run


def visible(company: Company, row_company: str | None) -> bool:
    """True when the viewer may see a record stamped *row_company*.

    The install-wide view (``company is None``) sees everything. A company sees only
    records stamped with its own id: an unstamped record is install-wide or legacy and
    never matches, so naming an agent (a string anyone can choose) reveals nothing.
    """
    return company is None or row_company == company


def _claim_row(claim: WorkClaim) -> ClaimRow:
    return ClaimRow(**claim_payload(claim))


def _waiter_rows(scope: str, queue: list[Waiter], company: Company) -> list[WaiterRow]:
    return [
        WaiterRow(
            scope=scope,
            position=i,
            agent_id=w.agent_id,
            task_id=w.task_id,
            mode=w.mode,
            intent=w.intent,
            priority=w.priority,
            joined_at=w.joined_at,
            expires_at=w.expires_at,
            company_id=w.company_id,
        )
        for i, w in enumerate(queue, start=1)
        if visible(company, w.company_id)
    ]


async def _claims(company: Company, kind: str | None) -> list[ClaimRow]:
    held = await _read(SOURCE_CLAIMS, lambda: list_claims(kind))
    rows = [_claim_row(c) for c in held if visible(company, c.company_id)]
    return sorted(rows, key=lambda r: (r.expires_at, r.scope))


async def _waiters(company: Company) -> list[WaiterRow]:
    queues = await _read(SOURCE_WAITLISTS, all_waiters)
    return [row for scope, queue in sorted(queues.items()) for row in _waiter_rows(scope, queue, company)]


async def claims(company: Company = None, kind: str | None = None) -> ClaimsResponse:
    rows = await _claims(company, kind)
    return ClaimsResponse(claims=rows, count=len(rows))


async def waitlists(company: Company = None) -> WaitlistsResponse:
    rows = await _waiters(company)
    return WaitlistsResponse(waiters=rows, count=len(rows))


async def contention() -> ContentionResponse:
    """Per shared resource (provider, cpu, queue scope): who holds it and who waits. Install-wide."""
    holders = [c for kind in RESOURCE_KINDS for c in await _claims(None, kind)]
    waiting = [w for w in await _waiters(None) if w.scope.split(":", 1)[0] in RESOURCE_KINDS]
    scopes = sorted({c.scope for c in holders} | {w.scope for w in waiting})
    rows = []
    for scope in scopes:
        held, queued = [c for c in holders if c.scope == scope], [w for w in waiting if w.scope == scope]
        rows.append(
            ContentionRow(
                scope=scope, kind=scope.split(":", 1)[0], holders=held, waiters=queued, contended=bool(queued)
            )
        )
    return ContentionResponse(resources=rows, count=len(rows))


def _refused_release(event: dict[str, Any], company: Company) -> ConflictRow | None:
    """A release aimed at another holder's claim, shown to each party with only its OWN side filled in.

    The actor sees its own ids, the holder sees its own; neither learns the other company's
    agent or task ids. A viewer that is neither party sees nothing.
    """
    actor, holder = visible(company, event.get("company_id")), visible(company, event.get("holder_company_id"))
    if not (actor or holder):
        return None
    return ConflictRow(
        at=event["at"],
        kind="release_refused",
        scope=event.get("scope"),
        agent_id=event.get("agent_id") if actor else None,
        task_id=event.get("task_id") if actor else None,
        other_agent_id=event.get("holder_agent_id") if holder else None,
        detail=f"a release of {event.get('scope')} was aimed at a claim held by another holder",
    )


def _event_conflict(event: dict[str, Any], company: Company) -> ConflictRow | None:
    if event["type"] == RELEASE_REFUSED:
        return _refused_release(event, company)
    if event["type"] == CLAIM_EXPIRED and visible(company, event.get("company_id")):
        return ConflictRow(
            at=event["at"],
            kind="claim_expired",
            scope=event.get("scope"),
            agent_id=event.get("agent_id"),
            task_id=event.get("task_id"),
            detail=f"{event.get('scope')} lapsed at its TTL without being released",
        )
    return None


def _yield_conflicts(events: list[dict[str, Any]], company: Company) -> list[ConflictRow]:
    pending = unanswered_yields(events, now_epoch=time.time(), timeout_s=YIELD_TIMEOUT_S)
    return [
        ConflictRow(
            at=e["at"],
            kind="yield_unanswered",
            scope=e.get("scope"),
            agent_id=e.get("requester_agent_id"),
            task_id=e.get("requester_task_id"),
            detail="asked the holder to release; no answer, so the claim is held",
        )
        for e in pending
        if visible(company, e.get("company_id"))
    ]


async def _lapsed_dev_loop() -> list[ConflictRow]:
    """Dev-loop actions that finished after their exclusive claim had lapsed (install-wide only)."""
    issues = await _read(SOURCE_DEV_LOOP, _dev_loop(dev_loop_actions.issues_with_history))
    rows: list[ConflictRow] = []
    for issue in issues:
        for a in await _read(SOURCE_DEV_LOOP, _dev_loop(functools.partial(dev_loop_actions.recent, issue))):
            if a.outcome == dev_loop_actions.OUTCOME_RAN_CLAIM_LAPSED:
                rows.append(
                    ConflictRow(
                        at=a.at,
                        kind="claim_lapsed_during_action",
                        scope=f"issue:{a.issue}",
                        detail=a.reason or a.intent,
                    )
                )
    return rows


async def conflicts(company: Company = None) -> ConflictsResponse:
    """Refused releases, claims that expired while held, unanswered yields, lapsed dev-loop actions.

    The last needs the dev-loop history, which names no company; it is included
    only for the install-wide view (``company=None``).
    """
    events = await _read(SOURCE_EVENTS, _events)
    rows = [row for e in events if (row := _event_conflict(e, company))] + _yield_conflicts(events, company)
    if company is None:
        rows += await _lapsed_dev_loop()
    rows.sort(key=lambda r: _when(r.at), reverse=True)
    return ConflictsResponse(conflicts=rows, count=len(rows))


async def _events() -> list[dict[str, Any]]:
    client = await get_async_redis_client(database="main")
    if client is None:
        raise ClaimUnavailable("ledger events: Redis client unavailable")
    return [e for e in await read_events(client) if _valid_event(e)]


def _valid_event(event: Any) -> bool:
    """An event the readers can order and classify: a dict with a string ``type`` and an ISO ``at``."""
    try:
        ok = isinstance(event, dict) and isinstance(event.get("type"), str)
        if ok:
            _when(event["at"])
    except (KeyError, TypeError, ValueError):
        ok = False
    if not ok:
        logger.warning("agent ledger: skipping malformed event %r", event)
    return ok


def _when(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def _event_activity(event: dict[str, Any], company: Company) -> ActivityRow | None:
    if not visible(company, event.get("company_id")):
        return None
    return ActivityRow(
        at=event["at"],
        type=event["type"],
        scope=event.get("scope"),
        agent_id=event.get("agent_id") or event.get("requester_agent_id"),
        task_id=event.get("task_id") or event.get("requester_task_id"),
        detail=event.get("decision") or event.get("reason") or "",
    )


async def activity(company: Company = None, limit: int = EVENT_CAP) -> ActivityResponse:
    """Recent coordination activity, newest first: claims taken, queues joined, recorded events.

    Built from what the stores keep -- a held claim's ``acquired_at``, a waiter's
    ``joined_at`` and the ledger event list. A claim taken and released between
    two reads leaves no row; the registry does not keep one.
    """
    held, waiting = await _claims(company, None), await _waiters(company)
    events = await _read(SOURCE_EVENTS, _events)
    rows = [
        ActivityRow(
            at=c.acquired_at, type="claim_held", scope=c.scope, agent_id=c.agent_id, task_id=c.task_id, detail=c.intent
        )
        for c in held
    ]
    rows += [
        ActivityRow(
            at=w.joined_at, type="waiting", scope=w.scope, agent_id=w.agent_id, task_id=w.task_id, detail=w.intent
        )
        for w in waiting
    ]
    rows += [row for e in events if (row := _event_activity(e, company))]
    rows.sort(key=lambda r: _when(r.at), reverse=True)
    rows = rows[: max(limit, 1)]
    return ActivityResponse(activity=rows, count=len(rows))


async def dev_loop_issues() -> DevLoopIssuesResponse:
    issues = await _read(SOURCE_DEV_LOOP, _dev_loop(dev_loop_actions.issues_with_history))
    return DevLoopIssuesResponse(issues=issues, count=len(issues))


async def dev_loop_history(issue: int, limit: int = dev_loop_actions.DEFAULT_RECENT_LIMIT) -> DevLoopHistoryResponse:
    actions = await _read(SOURCE_DEV_LOOP, _dev_loop(lambda: dev_loop_actions.recent(issue, limit=limit)))
    rows = [DevLoopActionRow(**dev_loop_actions.action_payload(a)) for a in actions]
    return DevLoopHistoryResponse(issue=issue, actions=rows, count=len(rows))
