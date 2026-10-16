# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM agent ledger: every company's agent coordination in one admin view (#18391).

Read-only and admin only. The data is install-wide, so it lives here and not in
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

from fastapi import APIRouter, Depends, Path, Query

from autobot_shared.auth.permissions import Permission
from autobot_shared.coordination import ledger_read
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
)
from services.auth import require_permission

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
