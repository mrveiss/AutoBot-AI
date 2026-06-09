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

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from user_management.database import get_async_session_factory

from ..models.enums import ApprovalStatus, ApprovalType
from ..services.approval import (
    ApprovalNotFoundError,
    ApprovalRequiredError,
    ApprovalService,
    ApprovalStateError,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/approvals", tags=["llc-approvals"])
_get_service = lazy_singleton(ApprovalService)


def _service() -> ApprovalService:
    return _get_service()


async def get_session() -> AsyncSession:
    factory = get_async_session_factory()
    async with factory() as session:
        yield session


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
# Endpoints
# ------------------------------------------------------------------


@router.post("", response_model=ApprovalResponse, status_code=201)
async def request_approval(
    body: ApprovalRequest,
    session: AsyncSession = Depends(get_session),
    svc: ApprovalService = Depends(_service),
) -> ApprovalResponse:
    """Create a pending approval gate record."""
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
) -> List[ApprovalResponse]:
    """List pending approvals for a company."""
    try:
        cid = uuid.UUID(company_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid company_id UUID")

    approvals = await svc.get_pending(session, cid, gate_type=type)
    return [_to_response(a) for a in approvals]


@router.post("/{approval_id}/decide", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    session: AsyncSession = Depends(get_session),
    svc: ApprovalService = Depends(_service),
) -> ApprovalResponse:
    """Approve or reject a pending approval."""
    try:
        aid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid approval_id UUID")

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
