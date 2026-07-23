# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC label management API routes (GH#8254).

Routes:
  POST   /api/llc/companies/{company_id}/labels
  GET    /api/llc/companies/{company_id}/labels
  PATCH  /api/llc/companies/{company_id}/labels/{label_id}
  DELETE /api/llc/companies/{company_id}/labels/{label_id}
  POST   /api/llc/companies/{company_id}/labels/work-items/{work_item_id}/labels
  DELETE /api/llc/companies/{company_id}/labels/work-items/{work_item_id}/labels/{label_id}

Auth / tenant isolation (GH#12148): every handler requires an authenticated
user and an organization context matching the ``{company_id}`` path segment.
Object-keyed operations additionally verify that the label / work item / label
set belongs to that company (IDOR guard).
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from llc.deps import get_session, service_dep
from user_management.services import TenantContext

from ..models.label import LLCLabel
from ..models.work_item import LLCWorkItem
from ..services.label_service import (
    LabelNameConflict,
    LabelNotFound,
    LLCLabelService,
    WorkItemNotFound,
    _label_to_dict,
)

router = APIRouter(prefix="/companies/{company_id}/labels", tags=["llc-labels"])
_service = service_dep(LLCLabelService)


# ------------------------------------------------------------------
# Auth / tenant isolation (GH#12148)
# ------------------------------------------------------------------


def _assert_company_match(ctx: TenantContext, company_id: str) -> None:
    """Reject cross-tenant access to a company-scoped label request (GH#12148).

    404 (not 403) so a cross-tenant caller can't distinguish "not my company"
    from "doesn't exist" — matches goals.py/budget.py (GH#12136). Platform
    admins are exempt.
    """
    if company_id != str(ctx.org_id) and not ctx.is_platform_admin:
        raise HTTPException(status_code=404, detail="Company not found")


async def _assert_label_in_company(session: AsyncSession, label_id: str, company_id: str) -> None:
    """404 unless *label_id* exists and belongs to *company_id* (IDOR guard)."""
    label = await _service().get(session, label_id)
    if label is None or str(label.company_id) != company_id:
        raise HTTPException(status_code=404, detail="Label not found")


async def _assert_work_item_in_company(session: AsyncSession, work_item_id: str, company_id: str) -> None:
    """404 unless *work_item_id* exists and belongs to *company_id* (IDOR guard)."""
    result = await session.execute(select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)))
    work_item = result.scalar_one_or_none()
    if work_item is None or str(work_item.company_id) != company_id:
        raise HTTPException(status_code=404, detail="Work item not found")


async def _assert_labels_in_company(session: AsyncSession, label_ids: List[str], company_id: str) -> None:
    """404 unless every id in *label_ids* is a label owned by *company_id* (IDOR guard)."""
    wanted = {uuid.UUID(lid) for lid in label_ids}
    if not wanted:
        return
    result = await session.execute(
        select(func.count())
        .select_from(LLCLabel)
        .where(LLCLabel.id.in_(wanted), LLCLabel.company_id == uuid.UUID(company_id))
    )
    if int(result.scalar_one()) != len(wanted):
        raise HTTPException(status_code=404, detail="Label not found")


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class LabelCreate(BaseModel):
    name: str = Field(..., max_length=128)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    description: Optional[str] = None
    created_by: Optional[str] = None


class LabelUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    description: Optional[str] = None


class LabelAssign(BaseModel):
    label_ids: List[str]
    assigned_by: Optional[str] = None


# ------------------------------------------------------------------
# Routes — label CRUD
# ------------------------------------------------------------------


@router.post("", status_code=201)
async def create_label(
    company_id: str,
    body: LabelCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    _assert_company_match(ctx, company_id)
    try:
        label = await _service().create(
            session,
            company_id=company_id,
            name=body.name,
            color=body.color,
            description=body.description,
            created_by=body.created_by,
        )
        await session.commit()
        return _label_to_dict(label)
    except LabelNameConflict:
        raise HTTPException(status_code=409, detail="Label name already exists for this company")


@router.get("")
async def list_labels(
    company_id: str,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[Dict[str, Any]]:
    _assert_company_match(ctx, company_id)
    return await _service().list_labels(session, company_id=company_id)


@router.patch("/{label_id}")
async def update_label(
    company_id: str,
    label_id: str,
    body: LabelUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    _assert_company_match(ctx, company_id)
    await _assert_label_in_company(session, label_id, company_id)
    try:
        label = await _service().update(
            session,
            label_id=label_id,
            name=body.name,
            color=body.color,
            description=body.description,
        )
        await session.commit()
        return _label_to_dict(label)
    except LabelNotFound:
        raise HTTPException(status_code=404, detail="Label not found")
    except LabelNameConflict:
        raise HTTPException(status_code=409, detail="Label name already exists for this company")


@router.delete("/{label_id}", status_code=204)
async def delete_label(
    company_id: str,
    label_id: str,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    _assert_company_match(ctx, company_id)
    await _assert_label_in_company(session, label_id, company_id)
    try:
        await _service().delete(session, label_id=label_id)
        await session.commit()
    except LabelNotFound:
        raise HTTPException(status_code=404, detail="Label not found")


# ------------------------------------------------------------------
# Routes — label assignment
# ------------------------------------------------------------------


@router.post("/work-items/{work_item_id}/labels", status_code=201)
async def assign_labels(
    company_id: str,
    work_item_id: str,
    body: LabelAssign,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    _assert_company_match(ctx, company_id)
    await _assert_work_item_in_company(session, work_item_id, company_id)
    await _assert_labels_in_company(session, body.label_ids, company_id)
    try:
        assigned = await _service().assign_labels(
            session,
            work_item_id=work_item_id,
            label_ids=body.label_ids,
            assigned_by=body.assigned_by,
        )
        await session.commit()
        return {
            "work_item_id": work_item_id,
            "assigned": [str(a.label_id) for a in assigned],
        }
    except WorkItemNotFound:
        raise HTTPException(status_code=404, detail="Work item not found")


@router.delete("/work-items/{work_item_id}/labels/{label_id}", status_code=204)
async def remove_label(
    company_id: str,
    work_item_id: str,
    label_id: str,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    _assert_company_match(ctx, company_id)
    await _assert_work_item_in_company(session, work_item_id, company_id)
    try:
        await _service().remove_label(
            session,
            work_item_id=work_item_id,
            label_id=label_id,
        )
        await session.commit()
    except WorkItemNotFound:
        raise HTTPException(status_code=404, detail="Work item not found")
