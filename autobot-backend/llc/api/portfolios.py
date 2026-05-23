# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC portfolio API routes (GH#8219).

Routes:
  GET    /llc/portfolios                  — list portfolios for a company
  POST   /llc/portfolios                  — create portfolio
  GET    /llc/portfolios/{id}             — get single portfolio
  PATCH  /llc/portfolios/{id}             — update portfolio fields
  DELETE /llc/portfolios/{id}             — delete portfolio + cascade
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.database import get_async_session

from ..services.portfolio import PortfolioService

router = APIRouter(prefix="/portfolios", tags=["llc-portfolios"])

_svc = PortfolioService()


# ------------------------------------------------------------------ Schemas


class PortfolioCreate(BaseModel):
    company_id: str
    name: str
    description: Optional[str] = None
    status: str = "active"


class PortfolioUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class PortfolioResponse(BaseModel):
    id: uuid.UUID
    company_id: str
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ------------------------------------------------------------------ Routes


@router.get("", response_model=List[PortfolioResponse])
async def list_portfolios(
    company_id: str = Query(..., description="Company ID"),
    status: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_async_session),
) -> List[PortfolioResponse]:
    rows = await _svc.list_by_company(session, company_id, status=status)
    return [PortfolioResponse.model_validate(r) for r in rows]


@router.post("", response_model=PortfolioResponse, status_code=201)
async def create_portfolio(
    body: PortfolioCreate,
    session: AsyncSession = Depends(get_async_session),
) -> PortfolioResponse:
    row = await _svc.create(
        session,
        company_id=body.company_id,
        name=body.name,
        description=body.description,
        status=body.status,
    )
    return PortfolioResponse.model_validate(row)


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(
    portfolio_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> PortfolioResponse:
    row = await _svc.get(session, portfolio_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return PortfolioResponse.model_validate(row)


@router.patch("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    portfolio_id: uuid.UUID,
    body: PortfolioUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> PortfolioResponse:
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    row = await _svc.update(session, portfolio_id, **updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return PortfolioResponse.model_validate(row)


@router.delete("/{portfolio_id}", status_code=204)
async def delete_portfolio(
    portfolio_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    deleted = await _svc.delete(session, portfolio_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Portfolio not found")
