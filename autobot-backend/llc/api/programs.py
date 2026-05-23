# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC program API routes (GH#8219).

Routes:
  GET    /llc/programs                   — list programs for a portfolio
  POST   /llc/programs                   — create program
  GET    /llc/programs/{id}              — get single program
  PATCH  /llc/programs/{id}              — update program fields
  DELETE /llc/programs/{id}              — delete program + cascade
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.database import get_async_session

from ..services.program import ProgramService

router = APIRouter(prefix="/programs", tags=["llc-programs"])

_svc = ProgramService()


# ------------------------------------------------------------------ Schemas


class ProgramCreate(BaseModel):
    portfolio_id: uuid.UUID
    name: str
    description: Optional[str] = None
    status: str = "active"


class ProgramUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class ProgramResponse(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ------------------------------------------------------------------ Routes


@router.get("", response_model=List[ProgramResponse])
async def list_programs(
    portfolio_id: uuid.UUID = Query(..., description="Portfolio ID"),
    status: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_async_session),
) -> List[ProgramResponse]:
    rows = await _svc.list_by_portfolio(session, portfolio_id, status=status)
    return [ProgramResponse.model_validate(r) for r in rows]


@router.post("", response_model=ProgramResponse, status_code=201)
async def create_program(
    body: ProgramCreate,
    session: AsyncSession = Depends(get_async_session),
) -> ProgramResponse:
    row = await _svc.create(
        session,
        portfolio_id=body.portfolio_id,
        name=body.name,
        description=body.description,
        status=body.status,
    )
    return ProgramResponse.model_validate(row)


@router.get("/{program_id}", response_model=ProgramResponse)
async def get_program(
    program_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> ProgramResponse:
    row = await _svc.get(session, program_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return ProgramResponse.model_validate(row)


@router.patch("/{program_id}", response_model=ProgramResponse)
async def update_program(
    program_id: uuid.UUID,
    body: ProgramUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> ProgramResponse:
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    row = await _svc.update(session, program_id, **updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return ProgramResponse.model_validate(row)


@router.delete("/{program_id}", status_code=204)
async def delete_program(
    program_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    deleted = await _svc.delete(session, program_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Program not found")
