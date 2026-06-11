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
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from llc.deps import get_session, service_dep

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
) -> Dict[str, Any]:
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
) -> List[Dict[str, Any]]:
    return await _service().list_labels(session, company_id=company_id)


@router.patch("/{label_id}")
async def update_label(
    company_id: str,
    label_id: str,
    body: LabelUpdate,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
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
) -> None:
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
) -> Dict[str, Any]:
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
) -> None:
    try:
        await _service().remove_label(
            session,
            work_item_id=work_item_id,
            label_id=label_id,
        )
        await session.commit()
    except WorkItemNotFound:
        raise HTTPException(status_code=404, detail="Work item not found")
