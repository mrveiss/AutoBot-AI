# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM agent ledger: every company's agent coordination in one admin view (#18391).

Read-only and admin only, but for one write: asking a claim's holder to release (#18599), which only
publishes a request and never releases anything. The data is install-wide, so it lives here and not in
the user backend (owner rule: server-wide data is SLM's). What this module can
read is what the shared Redis holds -- work claims and their renewals, the
waitlists, the dev-loop action history and the ledger event list. It reads them
through the same `autobot_shared.coordination` modules the user backend uses, so
the two views cannot disagree about what a row means.

NOT REACHABLE FROM HERE, and reported as such by ``GET /api/monitoring/agent-ledger/sources``
rather than shown as empty: agent presence, AI-stack agents, live sessions,
pending peer messages and idle subscriptions. Each is process-local state in the
user backend (`protocols/agent_presence.py`, `protocols/peer_inbox.py`,
`protocols/idle_notice.py`) with no cross-process store, and the registry
deliberately exposes no unscoped all-tenant query. Claims name an agent, not a
company, and the org chart that maps one to the other is in the user backend's
database, so rows here are not attributed to a company.

An unreachable store answers HTTP 503 with a typed body, never an empty list.
"""

from __future__ import annotations

import functools
import json
from typing import Any

from fastapi import APIRouter, Depends, Path, Query

from autobot_shared.auth.permissions import Permission
from autobot_shared.coordination import ledger_read
from autobot_shared.coordination.ledger_events import record_ledger_event
from autobot_shared.coordination.ledger_http import UNAVAILABLE_RESPONSES, serve_ledger, valid_kind
from autobot_shared.coordination.ledger_schemas import (
    ActivityResponse,
    ClaimsResponse,
    ConflictsResponse,
    ContentionResponse,
    DevLoopHistoryResponse,
    DevLoopIssuesResponse,
    LedgerSourcesResponse,
    LedgerSourceStatus,
    WaitlistsResponse,
    YieldRequestBody,
    YieldRequestResponse,
)
from autobot_shared.coordination.work_claims import ClaimUnavailable
from autobot_shared.coordination.yield_ask import TASK_EVENTS_CHANNEL, ask_holder_to_release, issue_yield_request
from autobot_shared.redis_client import get_async_redis_client
from services.auth import get_current_user, require_permission

#: Module-level so a test can override the exact dependency the routes carry.
require_ledger_admin = require_permission(Permission.ADMIN_SYSTEM)

router = APIRouter(prefix="/agent-ledger", tags=["agent-ledger"], responses=UNAVAILABLE_RESPONSES)
router.dependencies.append(Depends(require_ledger_admin))

_PROCESS_LOCAL = "process-local state in the user backend; there is no cross-process store the SLM can read"
#: Sources the SLM cannot read, with the precise reason (not probed -- they cannot be).
UNREACHABLE_SOURCES = {
    "presence": _PROCESS_LOCAL + " (the presence registry has no all-tenant query by design)",
    "ai_stack_agents": _PROCESS_LOCAL,
    "live_sessions": _PROCESS_LOCAL,
    "peer_messages": _PROCESS_LOCAL,
    "idle_subscribers": _PROCESS_LOCAL,
}


@router.get("/sources", response_model=LedgerSourcesResponse)
async def ledger_sources() -> LedgerSourcesResponse:
    """Which coordination stores this view can read right now, and which it never can."""
    probes = {
        ledger_read.SOURCE_CLAIMS: ledger_read.claims,
        ledger_read.SOURCE_WAITLISTS: ledger_read.waitlists,
        ledger_read.SOURCE_EVENTS: ledger_read.activity,
        ledger_read.SOURCE_DEV_LOOP: ledger_read.dev_loop_issues,
    }
    rows = []
    for source, probe in probes.items():
        try:
            await probe()
            rows.append(LedgerSourceStatus(source=source, reachable=True))
        except ledger_read.LedgerUnreadable as exc:
            rows.append(LedgerSourceStatus(source=source, reachable=False, reason=exc.detail))
    rows += [LedgerSourceStatus(source=name, reachable=False, reason=why) for name, why in UNREACHABLE_SOURCES.items()]
    return LedgerSourcesResponse(sources=rows)


@router.get("/claims", response_model=ClaimsResponse)
@serve_ledger
async def ledger_claims(kind: str | None = Query(None, description="Only claims of this scope kind")) -> ClaimsResponse:
    """Every held claim across the install: scope, mode, intent, expiry, renewals."""
    return await ledger_read.claims(None, valid_kind(kind))


@router.get("/waitlists", response_model=WaitlistsResponse)
@serve_ledger
async def ledger_waitlists() -> WaitlistsResponse:
    """Every queued agent behind a held scope, in position order."""
    return await ledger_read.waitlists(None)


@router.get("/contention", response_model=ContentionResponse)
@serve_ledger
async def ledger_contention() -> ContentionResponse:
    """Shared-resource scopes (provider, cpu, queue): holders and who waits."""
    return await ledger_read.contention()


@router.get("/conflicts", response_model=ConflictsResponse)
@serve_ledger
async def ledger_conflicts() -> ConflictsResponse:
    """Refused releases, claims expired while held, unanswered yields, lapsed dev-loop actions."""
    return await ledger_read.conflicts(None)


@router.get("/activity", response_model=ActivityResponse)
@serve_ledger
async def ledger_activity(limit: int = Query(100, ge=1, le=500)) -> ActivityResponse:
    """Recent coordination activity across the install, newest first."""
    return await ledger_read.activity(None, limit)


@router.get("/dev-loop", response_model=DevLoopIssuesResponse)
@serve_ledger
async def ledger_dev_loop_issues() -> DevLoopIssuesResponse:
    """Issues the dev loop has a recorded action history for."""
    return await ledger_read.dev_loop_issues()


@router.get("/dev-loop/{issue}", response_model=DevLoopHistoryResponse)
@serve_ledger
async def ledger_dev_loop_history(
    issue: int = Path(ge=1), limit: int = Query(20, ge=1, le=200)
) -> DevLoopHistoryResponse:
    """One issue's dev-loop action history, newest first, including refused and skipped attempts."""
    return await ledger_read.dev_loop_history(issue, limit)


async def _redis() -> Any:
    client = await get_async_redis_client(database="main")
    if client is None:
        raise ClaimUnavailable("agent ledger: Redis client unavailable; the request cannot be sent")
    return client


async def _publish(task_id: str, payload: dict[str, Any]) -> None:
    """Put the request on the holder's task channel -- the same pub/sub channel the user backend publishes to."""
    await (await _redis()).publish(TASK_EVENTS_CHANNEL.format(task_id), json.dumps(payload))


async def _record(event_type: str, **fields: Any) -> None:
    await record_ledger_event(await _redis(), event_type, **fields)


@router.post(
    "/claims/yield-request",
    response_model=YieldRequestResponse,
    responses={404: {"description": "No such claim"}, 429: {"description": "Asked too recently"}},
)
@serve_ledger
async def ledger_yield_request(body: YieldRequestBody, user: dict = Depends(get_current_user)) -> YieldRequestResponse:
    """Ask the holder of any claim to release it. Publishes a request; releases nothing."""
    token = await ask_holder_to_release(
        None,
        user_id=str(user.get("sub")),
        scope=body.scope,
        holder_task_id=body.holder_task_id,
        reason=body.reason,
        issue=functools.partial(issue_yield_request, publish=_publish, record=_record),
    )
    return YieldRequestResponse(token=token)
