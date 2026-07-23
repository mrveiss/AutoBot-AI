# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC board approval gates API routes (GH#8214).

Routes:
  POST   /api/llc/approvals               — request approval
  GET    /api/llc/approvals               — list pending (company_id required)
  POST   /api/llc/approvals/{id}/decide   — approve or reject

Access control: every route requires an authenticated session whose tenant
(``TenantContext.org_id``) matches the target company — either the
``company_id`` supplied directly, or the company owning the requested
``approval_id`` (GH#12163). Platform admins are exempt. 404 (not 403) is used
on mismatch so a cross-tenant caller can't distinguish "not my company" from
"doesn't exist" — matches the goals.py/secrets.py idiom (GH#12136, GH#12147).
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.logging_manager import get_logger
from llc.deps import get_session, service_dep
from user_management.services import TenantContext

from ..models.approval import LLCApproval
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


_BOARD_SENTINEL = uuid.UUID("00000000-0000-0000-0000-000000000001")


class ApprovalDecision(BaseModel):
    decision: ApprovalStatus
    # Optional: callers may pass the deciding user/agent UUID.  Board UI
    # decision-makers are human users whose IDs are passed here; falls back to
    # the board sentinel so the field is never null in the DB (GH#8552).
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
# Auth / tenant isolation (GH#12163)
# ------------------------------------------------------------------


def _assert_company_match(ctx: TenantContext, company_id: Any) -> None:
    """Reject cross-tenant access to a company-scoped approval request.

    404 (not 403) so a cross-tenant caller can't distinguish "not my company"
    from "doesn't exist" — matches goals.py/secrets.py (GH#12136, GH#12147).
    Platform admins are exempt.
    """
    if str(company_id) != str(ctx.org_id) and not ctx.is_platform_admin:
        raise HTTPException(status_code=404, detail="Company not found")


async def _get_authorized_approval(session: AsyncSession, approval_id: uuid.UUID, ctx: TenantContext) -> LLCApproval:
    """Load an approval and enforce tenant isolation; 404 if missing or cross-tenant."""
    result = await session.execute(select(LLCApproval).where(LLCApproval.id == approval_id))
    approval = result.scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    _assert_company_match(ctx, approval.company_id)
    return approval


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
    _assert_company_match(ctx, body.company_id)
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

    _assert_company_match(ctx, cid)
    approvals = await svc.get_pending(session, cid, gate_type=type)
    return [_to_response(a) for a in approvals]


@router.post("/{approval_id}/decide", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    session: AsyncSession = Depends(get_session),
    svc: ApprovalService = Depends(_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ApprovalResponse:
    """Approve or reject a pending approval."""
    try:
        aid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid approval_id UUID")

    await _get_authorized_approval(session, aid, ctx)

    try:
        async with session.begin():
            approval = await svc.decide(
                session,
                approval_id=aid,
                decision=body.decision,
                decided_by=body.decided_by_agent_id or _BOARD_SENTINEL,
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


def _to_response(approval: Any) -> ApprovalResponse:
    return ApprovalResponse(
        id=str(approval.id),
        company_id=str(approval.company_id),
        type=approval.type,
        status=approval.status,
        requested_by_agent_id=str(approval.requested_by_agent_id),
        payload=approval.payload or {},
        decided_by_agent_id=(str(approval.decided_by_agent_id) if approval.decided_by_agent_id else None),
        decided_at=approval.decided_at.isoformat() if approval.decided_at else None,
        created_at=approval.created_at.isoformat(),
        updated_at=approval.updated_at.isoformat(),
    )


__all__ = ["router"]
