# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC review gate policy API routes (GH#8234).

Routes:
  GET    /api/llc/companies/{company_id}/review-gate-policies
  POST   /api/llc/companies/{company_id}/review-gate-policies
  PATCH  /api/llc/companies/{company_id}/review-gate-policies/{policy_id}
  DELETE /api/llc/companies/{company_id}/review-gate-policies/{policy_id}
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import WorkItemType
from ..services.review_gate import (
    ReviewGatePolicyConflictError,
    ReviewGatePolicyNotFoundError,
    ReviewGatePolicyService,
)
from llc.deps import get_session, service_dep

router = APIRouter(tags=["llc-review-gate-policies"])
_service = service_dep(ReviewGatePolicyService)


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class ReviewGatePolicyCreate(BaseModel):
    item_type: WorkItemType
    requires_human_review: bool = False
    reviewer_role: Optional[str] = None


class ReviewGatePolicyUpdate(BaseModel):
    requires_human_review: Optional[bool] = None
    reviewer_role: Optional[str] = None


class ReviewGatePolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    item_type: WorkItemType
    requires_human_review: bool
    reviewer_role: Optional[str]
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get(
    "/companies/{company_id}/review-gate-policies",
    response_model=List[ReviewGatePolicyRead],
)
async def list_review_gate_policies(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    svc: ReviewGatePolicyService = Depends(_service),
) -> List[ReviewGatePolicyRead]:
    policies = await svc.list_policies(session, str(company_id))
    return [ReviewGatePolicyRead.model_validate(p) for p in policies]


@router.post(
    "/companies/{company_id}/review-gate-policies",
    response_model=ReviewGatePolicyRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_review_gate_policy(
    company_id: uuid.UUID,
    body: ReviewGatePolicyCreate,
    session: AsyncSession = Depends(get_session),
    svc: ReviewGatePolicyService = Depends(_service),
) -> ReviewGatePolicyRead:
    try:
        policy = await svc.create_policy(
            session,
            str(company_id),
            body.item_type,
            requires_human_review=body.requires_human_review,
            reviewer_role=body.reviewer_role,
        )
        await session.commit()
    except ReviewGatePolicyConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Internal server error")
    return ReviewGatePolicyRead.model_validate(policy)


@router.patch(
    "/companies/{company_id}/review-gate-policies/{policy_id}",
    response_model=ReviewGatePolicyRead,
)
async def update_review_gate_policy(
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
    body: ReviewGatePolicyUpdate,
    session: AsyncSession = Depends(get_session),
    svc: ReviewGatePolicyService = Depends(_service),
) -> ReviewGatePolicyRead:
    try:
        policy = await svc.update_policy(
            session,
            str(policy_id),
            requires_human_review=body.requires_human_review,
            reviewer_role=body.reviewer_role,
        )
        await session.commit()
    except ReviewGatePolicyNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")
    return ReviewGatePolicyRead.model_validate(policy)


@router.delete(
    "/companies/{company_id}/review-gate-policies/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_review_gate_policy(
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    svc: ReviewGatePolicyService = Depends(_service),
) -> None:
    deleted = await svc.delete_policy(session, str(policy_id))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Policy {policy_id} not found")
    await session.commit()
