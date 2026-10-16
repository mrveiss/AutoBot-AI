# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company OS agent ledger: who is working on what, for the caller's company (#18391).

Read-only except one write. The routes show what the coordination stores already
hold -- presence (#16947), work claims, the waitlist (#15948), pending peer messages
(#16948) and idle subscriptions (#16949) -- and change none of it. There is no
force-release and no delete; claims are released by their holder, and the one
human action the design allows, asking a holder to release (#18599), only publishes
a request.

TENANCY. The company comes from `require_org_context`, never from a request
parameter. Presence, peer messages and idle subscriptions are keyed by tenant and
filtered to the caller's own. Claims, waiters and ledger events are scoped by the
company STAMPED on them when they were written (`autobot_shared/coordination/
claim_company.py`) -- not by agent name, which anyone can choose. A record with no
stamp (install-wide actors such as dev sessions and AI-stack roles, or anything
written before stamping) is invisible here and shown only in the SLM view.

An unreachable store answers HTTP 503 with a typed body, never an empty list
(`autobot_shared/coordination/ledger_http.py`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Query

from api.user_management.dependencies import get_current_user, get_current_user_id, require_org_context
from autobot_shared.coordination import ledger_read
from autobot_shared.coordination.ledger_http import UNAVAILABLE_RESPONSES, serve_ledger, valid_kind
from autobot_shared.coordination.ledger_schemas import (
    ActivityResponse,
    ClaimsResponse,
    ConflictsResponse,
    IdleSubscriberRow,
    IdleSubscribersResponse,
    PeerMessageRow,
    PeerMessagesResponse,
    PresenceResponse,
    PresenceRow,
    WaitlistsResponse,
    YieldRequestBody,
    YieldRequestResponse,
)
from autobot_shared.coordination.yield_ask import ask_holder_to_release
from protocols.agent_presence import get_presence_registry
from protocols.idle_notice import active_subscriptions
from protocols.peer_inbox import get_peer_inbox_directory
from services.claim_yield import request_yield
from user_management.services import TenantContext

router = APIRouter(dependencies=[Depends(get_current_user)], responses=UNAVAILABLE_RESPONSES)


@dataclass(frozen=True)
class CompanyScope:
    """The caller's company, from the verified tenant context."""

    org_id: str


async def company_scope(ctx: TenantContext = Depends(require_org_context)) -> CompanyScope:
    return CompanyScope(org_id=str(ctx.org_id))


@router.get("/ledger/presence", response_model=PresenceResponse)
@serve_ledger
async def ledger_presence(scope: CompanyScope = Depends(company_scope)) -> PresenceResponse:
    """The company's live agents plus shared infrastructure, busy or idle."""
    entries = get_presence_registry().list_live(scope.org_id)
    rows = [
        PresenceRow(
            kind=e.kind.value, tenant_id=e.tenant_id, name=e.name, busy=e.busy, detail=e.detail, last_seen=e.last_seen
        )
        for e in entries
    ]
    return PresenceResponse(agents=rows, count=len(rows))


@router.get("/ledger/claims", response_model=ClaimsResponse)
@serve_ledger
async def ledger_claims(
    kind: str | None = Query(None, description="Only claims of this scope kind"),
    scope: CompanyScope = Depends(company_scope),
) -> ClaimsResponse:
    """The company's held claims: scope, mode, intent, expiry and renewals."""
    return await ledger_read.claims(scope.org_id, valid_kind(kind))


@router.get("/ledger/waitlists", response_model=WaitlistsResponse)
@serve_ledger
async def ledger_waitlists(scope: CompanyScope = Depends(company_scope)) -> WaitlistsResponse:
    """The company's agents queued behind a scope someone else holds, in position order."""
    return await ledger_read.waitlists(scope.org_id)


@router.get("/ledger/conflicts", response_model=ConflictsResponse)
@serve_ledger
async def ledger_conflicts(scope: CompanyScope = Depends(company_scope)) -> ConflictsResponse:
    """Refused releases, claims that expired while held, and unanswered yield requests."""
    return await ledger_read.conflicts(scope.org_id)


@router.get("/ledger/activity", response_model=ActivityResponse)
@serve_ledger
async def ledger_activity(
    limit: int = Query(100, ge=1, le=500), scope: CompanyScope = Depends(company_scope)
) -> ActivityResponse:
    """Recent coordination activity for the company, newest first."""
    return await ledger_read.activity(scope.org_id, limit)


@router.get("/ledger/peer-messages", response_model=PeerMessagesResponse)
async def ledger_peer_messages(scope: CompanyScope = Depends(company_scope)) -> PeerMessagesResponse:
    """Messages waiting for the company's agents' next turn. Counts and senders, never content.

    Reads without draining. Only inboxes owned by this company: a shared
    infrastructure agent's inbox is not the company's to inspect.
    """
    rows = [
        PeerMessageRow(
            recipient_kind=kind.value,
            recipient_name=name,
            pending=len(queued),
            senders=sorted({m.sender.name for m in queued}),
            oldest_at=min(m.timestamp for m in queued),
        )
        for kind, name, queued in get_peer_inbox_directory().pending_for(scope.org_id)
    ]
    return PeerMessagesResponse(recipients=rows, count=len(rows))


@router.get("/ledger/idle-subscribers", response_model=IdleSubscribersResponse)
async def ledger_idle_subscribers(scope: CompanyScope = Depends(company_scope)) -> IdleSubscribersResponse:
    """Agents currently waiting to be told a company peer next goes idle."""
    rows = [
        IdleSubscriberRow(
            subscriber=s.subscriber,
            target_kind=s.kind.value,
            target_name=s.name,
            since=s.since,
            expires_at=s.expires_at,
        )
        for s in active_subscriptions()
        if s.tenant_id == scope.org_id
    ]
    return IdleSubscribersResponse(subscribers=rows, count=len(rows))


@router.post(
    "/ledger/claims/yield-request",
    response_model=YieldRequestResponse,
    responses={404: {"description": "No such claim for this caller"}, 429: {"description": "Asked too recently"}},
)
@serve_ledger
async def ledger_yield_request(
    body: YieldRequestBody,
    scope: CompanyScope = Depends(company_scope),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> YieldRequestResponse:
    """Ask the holder of one of the company's claims to release it. Publishes a request; releases nothing."""
    token = await ask_holder_to_release(
        scope.org_id,
        user_id=str(user_id),
        scope=body.scope,
        holder_task_id=body.holder_task_id,
        reason=body.reason,
        issue=request_yield,
    )
    return YieldRequestResponse(token=token)
