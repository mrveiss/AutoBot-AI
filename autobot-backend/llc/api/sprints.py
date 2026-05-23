# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC sprint API routes (GH#8219).

Routes:
  GET    /llc/sprints                    — list sprints for a project
  POST   /llc/sprints                    — create sprint
  GET    /llc/sprints/{id}               — get single sprint
  PATCH  /llc/sprints/{id}               — update sprint fields
  DELETE /llc/sprints/{id}               — delete sprint
  POST   /llc/sprints/{id}/start         — start sprint (planning → active)
  POST   /llc/sprints/{id}/close         — close sprint (active/review/retrospective → closed)
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.database import get_async_session

from ..models.enums import SprintStatus
from ..services.sprint import SprintService

router = APIRouter(prefix="/sprints", tags=["llc-sprints"])

_svc = SprintService()


# ------------------------------------------------------------------ Schemas


class SprintCreate(BaseModel):
    project_id: uuid.UUID
    name: str
    status: SprintStatus = SprintStatus.PLANNING
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    capacity_points: Optional[int] = None


class SprintUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[SprintStatus] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    capacity_points: Optional[int] = None
    velocity_actual: Optional[int] = None


class SprintCloseRequest(BaseModel):
    velocity_actual: Optional[int] = None


class SprintResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    status: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    capacity_points: Optional[int]
    velocity_actual: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ------------------------------------------------------------------ Routes


@router.get("", response_model=List[SprintResponse])
async def list_sprints(
    project_id: uuid.UUID = Query(..., description="Project ID"),
    status: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_async_session),
) -> List[SprintResponse]:
    rows = await _svc.list_by_project(session, project_id, status=status)
    return [SprintResponse.model_validate(r) for r in rows]


@router.post("", response_model=SprintResponse, status_code=201)
async def create_sprint(
    body: SprintCreate,
    session: AsyncSession = Depends(get_async_session),
) -> SprintResponse:
    row = await _svc.create(
        session,
        project_id=body.project_id,
        name=body.name,
        status=body.status,
        start_date=body.start_date,
        end_date=body.end_date,
        capacity_points=body.capacity_points,
    )
    return SprintResponse.model_validate(row)


@router.get("/{sprint_id}", response_model=SprintResponse)
async def get_sprint(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> SprintResponse:
    row = await _svc.get(session, sprint_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Sprint not found")
    return SprintResponse.model_validate(row)


@router.patch("/{sprint_id}", response_model=SprintResponse)
async def update_sprint(
    sprint_id: uuid.UUID,
    body: SprintUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> SprintResponse:
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if "status" in updates and isinstance(updates["status"], SprintStatus):
        updates["status"] = updates["status"].value
    row = await _svc.update(session, sprint_id, **updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Sprint not found")
    return SprintResponse.model_validate(row)


@router.delete("/{sprint_id}", status_code=204)
async def delete_sprint(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    deleted = await _svc.delete(session, sprint_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Sprint not found")


@router.post("/{sprint_id}/start", response_model=SprintResponse)
async def start_sprint(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> SprintResponse:
    row = await _svc.start(session, sprint_id)
    return SprintResponse.model_validate(row)


@router.post("/{sprint_id}/close", response_model=SprintResponse)
async def close_sprint(
    sprint_id: uuid.UUID,
    body: SprintCloseRequest = SprintCloseRequest(),
    session: AsyncSession = Depends(get_async_session),
) -> SprintResponse:
    row = await _svc.close(session, sprint_id, velocity_actual=body.velocity_actual)
    return SprintResponse.model_validate(row)
