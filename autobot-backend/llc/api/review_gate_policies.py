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

from api.user_management.dependencies import get_current_user, require_org_context
from llc.deps import assert_company_access, get_session, service_dep
from user_management.services import TenantContext

from ..models.enums import WorkItemType
from ..services.review_gate import (
    ReviewGatePolicyConflictError,
    ReviewGatePolicyNotFoundError,
    ReviewGatePolicyService,
)

router = APIRouter(tags=["llc-review-gate-policies"])
_service = service_dep(ReviewGatePolicyService)


# ------------------------------------------------------------------
# Auth / tenant isolation (GH#12148)
# ------------------------------------------------------------------


async def _get_authorized_policy(
    session: AsyncSession,
    svc: ReviewGatePolicyService,
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
    ctx: TenantContext,
):
    """Enforce tenant isolation and policy<->company ownership (IDOR fix).

    The service mutators key on ``policy_id`` alone, so a caller could pass
    their own ``company_id`` in the path (passing the tenant check) while
    targeting a ``policy_id`` owned by a different company. Load the policy and
    verify it belongs to the path company before mutating (GH#12148). This
    path-consistency check is intentionally NOT admin-exempt (unlike
    ``assert_company_access``): even a platform admin navigating
    /companies/{company_id}/review-gate-policies/{policy_id} must have the two
    path segments agree, so it stays local rather than folding into the
    generic loader.
    """
    assert_company_access(ctx, company_id)
    policy = await svc.get_policy_by_id(session, str(policy_id))
    if policy is None or str(policy.company_id) != str(company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Policy {policy_id} not found")
    return policy


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
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[ReviewGatePolicyRead]:
    assert_company_access(ctx, company_id)
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
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ReviewGatePolicyRead:
    assert_company_access(ctx, company_id)
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
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ReviewGatePolicyRead:
    await _get_authorized_policy(session, svc, company_id, policy_id, ctx)
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
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    await _get_authorized_policy(session, svc, company_id, policy_id, ctx)
    deleted = await svc.delete_policy(session, str(policy_id))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Policy {policy_id} not found")
    await session.commit()
