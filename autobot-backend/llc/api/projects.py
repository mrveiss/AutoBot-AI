# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC project API routes (GH#8219).

Routes:
  GET    /llc/projects                   — list projects for a program
  POST   /llc/projects                   — create project
  GET    /llc/projects/{id}              — get single project
  PATCH  /llc/projects/{id}              — update project fields
  DELETE /llc/projects/{id}              — delete project + cascade
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.database import get_async_session

from ..services.project import ProjectService

router = APIRouter(prefix="/projects", tags=["llc-projects"])

_svc = ProjectService()


# ------------------------------------------------------------------ Schemas


class ProjectCreate(BaseModel):
    program_id: uuid.UUID
    name: str
    description: Optional[str] = None
    status: str = "active"
    owner_agent_id: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    owner_agent_id: Optional[str] = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    program_id: uuid.UUID
    name: str
    description: Optional[str]
    status: str
    owner_agent_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ------------------------------------------------------------------ Routes


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    program_id: uuid.UUID = Query(..., description="Program ID"),
    status: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_async_session),
) -> List[ProjectResponse]:
    rows = await _svc.list_by_program(session, program_id, status=status)
    return [ProjectResponse.model_validate(r) for r in rows]


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_async_session),
) -> ProjectResponse:
    row = await _svc.create(
        session,
        program_id=body.program_id,
        name=body.name,
        description=body.description,
        status=body.status,
        owner_agent_id=body.owner_agent_id,
    )
    return ProjectResponse.model_validate(row)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> ProjectResponse:
    row = await _svc.get(session, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse.model_validate(row)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> ProjectResponse:
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    row = await _svc.update(session, project_id, **updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse.model_validate(row)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    deleted = await _svc.delete(session, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
