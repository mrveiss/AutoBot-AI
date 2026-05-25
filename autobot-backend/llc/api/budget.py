# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC per-agent budget API routes (GH#8215)."""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from llc.exceptions import BudgetExhausted
from llc.models.budget import LLCAgentBudget
from llc.services.budget import BudgetService
from user_management.database import get_async_session

router = APIRouter(prefix="/budget", tags=["llc-budget"])

# Separate router for /cost-events so it doesn't inherit the /budget prefix
cost_events_router = APIRouter(prefix="/cost-events", tags=["llc-cost-events"])


class BudgetResponse(BaseModel):
    agent_id: str
    budget_limit: Decimal
    budget_spent: Decimal
    alert_threshold: float
    remaining: Decimal
    is_over_limit: bool
    alert_triggered: bool

    model_config = {"from_attributes": True}


class IngestRequest(BaseModel):
    tokens_in: int
    tokens_out: int
    model: str


class IngestResponse(BaseModel):
    cost: Decimal


class UpdateLimitRequest(BaseModel):
    budget_limit: Decimal
    alert_threshold: Optional[float] = None


def _build_response(row: LLCAgentBudget, remaining: Decimal, is_over: bool, alert: bool) -> BudgetResponse:
    return BudgetResponse(
        agent_id=row.agent_id,
        budget_limit=Decimal(str(row.budget_limit)),
        budget_spent=Decimal(str(row.budget_spent)),
        alert_threshold=row.alert_threshold,
        remaining=remaining,
        is_over_limit=is_over,
        alert_triggered=alert,
    )


@router.get("", response_model=List[Dict[str, Any]])
async def list_budgets(
    company_id: str = Query(..., description="Filter by company UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> List[Dict[str, Any]]:
    """List all per-agent budget rows for a company (GH#8551 CostDashboard)."""
    result = await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.company_id == company_id))
    rows = result.scalars().all()
    svc = BudgetService()
    out: List[Dict[str, Any]] = []
    for row in rows:
        remaining, is_over, alert = await svc.check_budget(session, row.agent_id)
        out.append(
            {
                "agent_id": row.agent_id,
                "budget_limit": str(row.budget_limit),
                "budget_spent": str(row.budget_spent),
                "remaining": str(remaining),
                "is_over_limit": is_over,
                "alert_triggered": alert,
                "alert_threshold": row.alert_threshold,
            }
        )
    return out


@router.get("/{agent_id}", response_model=BudgetResponse)
async def get_budget(
    agent_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> BudgetResponse:
    # GH#8461: single SELECT — fetch the row directly and compute derived fields
    # here rather than calling check_budget() (which does its own SELECT) then
    # re-fetching the same row.
    result = await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == agent_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No budget row for agent {agent_id}")

    spent = Decimal(str(row.budget_spent))
    limit = Decimal(str(row.budget_limit))
    threshold = Decimal(str(row.alert_threshold))
    remaining = limit - spent
    is_over = spent > limit
    alert = limit > Decimal("0") and spent / limit >= threshold

    return _build_response(row, remaining, is_over, alert)


@router.post("/{agent_id}/ingest", response_model=IngestResponse)
async def ingest_cost(
    agent_id: str,
    body: IngestRequest,
    session: AsyncSession = Depends(get_async_session),
) -> IngestResponse:
    svc = BudgetService()
    try:
        cost = await svc.ingest_cost_event(session, agent_id, body.tokens_in, body.tokens_out, body.model)
    except BudgetExhausted as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    return IngestResponse(cost=cost)


@router.patch("/{agent_id}/limit", response_model=BudgetResponse)
async def update_limit(
    agent_id: str,
    body: UpdateLimitRequest,
    session: AsyncSession = Depends(get_async_session),
) -> BudgetResponse:
    result = await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == agent_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No budget row for agent {agent_id}")

    # GH#8462: pass Decimal directly — Pydantic already validates it as Decimal,
    # no str() conversion needed (which would silently coerce to TEXT in the ORM).
    values: dict = {"budget_limit": body.budget_limit}
    if body.alert_threshold is not None:
        values["alert_threshold"] = body.alert_threshold

    await session.execute(update(LLCAgentBudget).where(LLCAgentBudget.agent_id == agent_id).values(**values))
    await session.refresh(row)

    svc = BudgetService()
    remaining, is_over, alert = await svc.check_budget(session, agent_id)
    return _build_response(row, remaining, is_over, alert)


# ---------------------------------------------------------------------------
# /cost-events — CostDashboard list endpoint (GH#8551)
# ---------------------------------------------------------------------------


@cost_events_router.get("", response_model=List[Dict[str, Any]])
async def list_cost_events(
    company_id: str = Query(..., description="Filter by company UUID"),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_async_session),
) -> List[Dict[str, Any]]:
    """Return per-agent budget spend summary as cost events (GH#8551).

    Returns one entry per agent with non-zero spend in the given company.
    A dedicated cost-event store is not yet implemented; this derives the
    data from LLCAgentBudget rows.
    """
    result = await session.execute(
        select(LLCAgentBudget)
        .where(LLCAgentBudget.company_id == company_id)
        .order_by(LLCAgentBudget.agent_id)
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "agent_id": row.agent_id,
            "event_type": "budget_summary",
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd": str(row.budget_spent),
            "model": "unknown",
            "ts": None,
        }
        for row in rows
    ]
