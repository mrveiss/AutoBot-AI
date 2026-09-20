# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC board approval gates API routes (GH#8214).

Routes:
  POST   /api/llc/approvals               — request approval
  GET    /api/llc/approvals               — list pending (company_id required)
  POST   /api/llc/approvals/{id}/decide   — approve or reject
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from api.user_management.human_decider import require_interactive_human
from autobot_shared.logging_manager import get_logger
from llc.deps import assert_company_access, get_session, load_authorized, service_dep
from models.approval import Approval
from user_management.services import TenantContext

from ..models.enums import ApprovalStatus, ApprovalType
from ..services.approval import (
    ApprovalNotFoundError,
    ApprovalRequiredError,
    ApprovalService,
    ApprovalStateError,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/approvals", tags=["llc-approvals"])
_service = service_dep(ApprovalService)


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class ApprovalRequest(BaseModel):
    company_id: uuid.UUID
    type: ApprovalType
    requested_by_agent_id: uuid.UUID
    payload: Dict[str, Any] = {}


# Decider recorded before 2026-09-18 (#17042) when the client named nobody
# (GH#8552). Only historic rows carry it: decisions are now attributed to the
# verified caller, so read it as "decided before attribution was enforced".
_BOARD_SENTINEL = uuid.UUID("00000000-0000-0000-0000-000000000001")


class ApprovalDecision(BaseModel):
    decision: ApprovalStatus
    # Ignored since #17042: the decider is the verified caller, never the body.
    # Kept so older clients that still send it are logged rather than silently
    # accepted or rejected.
    decided_by_agent_id: Optional[uuid.UUID] = None


class ApprovalResponse(BaseModel):
    id: str
    company_id: str
    type: str
    status: str
    requested_by_agent_id: str
    payload: Dict[str, Any]
    decided_by_agent_id: Optional[str]
    decided_at: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("", response_model=ApprovalResponse, status_code=201)
async def request_approval(
    body: ApprovalRequest,
    session: AsyncSession = Depends(get_session),
    svc: ApprovalService = Depends(_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ApprovalResponse:
    """Create a pending approval gate record."""
    assert_company_access(ctx, body.company_id)
    async with session.begin():
        approval = await svc.request_approval(
            session,
            company_id=body.company_id,
            gate_type=body.type,
            payload=body.payload,
            requested_by=body.requested_by_agent_id,
        )
    await svc.publish_requested(approval)
    return _to_response(approval)


@router.get("", response_model=List[ApprovalResponse])
async def list_pending(
    company_id: str = Query(..., description="Filter by company"),
    type: Optional[ApprovalType] = Query(None, description="Filter by gate type"),
    session: AsyncSession = Depends(get_session),
    svc: ApprovalService = Depends(_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[ApprovalResponse]:
    """List pending approvals for a company."""
    try:
        cid = uuid.UUID(company_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid company_id UUID")

    assert_company_access(ctx, cid)
    approvals = await svc.get_pending(session, cid, gate_type=type)
    return [_to_response(a) for a in approvals]


@router.post("/{approval_id}/decide", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    session: AsyncSession = Depends(get_session),
    svc: ApprovalService = Depends(_service),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ApprovalResponse:
    """Approve or reject a pending approval, attributed to the verified caller (#17042)."""
    require_interactive_human(current_user, "LLC approval decision")
    decided_by = _verified_decider(ctx, body)
    try:
        aid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid approval_id UUID")

    # IDOR: derive the owning company from the row and tenant-check it before
    # allowing a decision (GH#12148).
    authorized = await load_authorized(session, Approval, aid, ctx, not_found_detail="Approval not found")
    # load_authorized's platform-admin exemption skips the company_id
    # comparison outright, so an admin could otherwise reach a NULL-company_id
    # (general, non-LLC) row through this LLC-scoped route (#17043 review) --
    # mutating it through LLC decision semantics and logging to
    # company:None:decisions. Refused here, same as any other cross-scope
    # row: 404, existence hidden.
    if authorized.company_id is None:
        raise HTTPException(status_code=404, detail="Approval not found")

    try:
        async with session.begin():
            approval = await svc.decide(
                session,
                approval_id=aid,
                decision=body.decision,
                decided_by=decided_by,
            )
    except ApprovalNotFoundError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=404, detail="Internal server error")
    except (ApprovalStateError, ApprovalRequiredError):
        raise HTTPException(status_code=409, detail="Internal server error")

    await svc.publish_decided(approval, body.decision)
    await svc.log_decision_to_kb(approval)  # GH#8243: index to decisions KB
    return _to_response(approval)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _verified_decider(ctx: TenantContext, body: ApprovalDecision) -> uuid.UUID:
    """The verified caller's user id; a client-supplied decider is ignored (#17042)."""
    if body.decided_by_agent_id is not None:
        logger.warning(
            "Ignoring client-supplied decided_by_agent_id=%s; recording the verified caller %s",
            body.decided_by_agent_id,
            ctx.user_id,
        )
    # Every interactive login carries a UUID user id (api/auth.py sets it from the
    # users table), so this refuses only a caller the system cannot name. If the
    # login payload ever stops carrying it, people are refused here, not misattributed.
    if ctx.user_id is None:
        raise HTTPException(status_code=403, detail="The decision cannot be attributed to a verified user")
    return ctx.user_id


def _to_response(approval: Any) -> ApprovalResponse:
    """Build the unchanged wire response from an ``Approval`` row (#17043).

    Field *names* on the wire (``type``, ``payload``, ``requested_by_agent_id``,
    ``decided_by_agent_id``) are the pre-merge contract; the attributes read
    off ``approval`` are the unified model's (``approval_type``, ``context``,
    ``requested_by_agent``, ``decided_by_user``).
    """
    return ApprovalResponse(
        id=str(approval.id),
        company_id=str(approval.company_id),
        type=approval.approval_type,
        status=approval.status,
        requested_by_agent_id=approval.requested_by_agent,
        payload=approval.context or {},
        decided_by_agent_id=approval.decided_by_user,
        decided_at=approval.decided_at.isoformat() if approval.decided_at else None,
        created_at=approval.created_at.isoformat(),
        updated_at=approval.updated_at.isoformat(),
    )


__all__ = ["router"]
