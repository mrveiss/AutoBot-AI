# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC per-agent budget API routes (GH#8215)."""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from llc.exceptions import BudgetExhausted
from llc.models.budget import LLCAgentBudget
from llc.services.budget import BudgetService
from user_management.database import get_async_session

logger = get_logger(__name__)
router = APIRouter(prefix="/budget", tags=["llc-budget"])

# Separate router for /cost-events so it doesn't inherit the /budget prefix
cost_events_router = APIRouter(prefix="/cost-events", tags=["llc-cost-events"])

# Separate router for per-company cost breakdown (GH#8486)
costs_by_model_router = APIRouter(prefix="/companies", tags=["llc-costs-by-model"])


class BudgetResponse(BaseModel):
    """Budget status response (GH#8215, GH#8997)."""

    agent_id: str
    budget_mode: str  # "dollars" or "tokens"

    # Dollar-based fields
    budget_limit: Decimal
    budget_spent: Decimal

    # Token-based fields (GH#8997)
    token_limit: int | None
    tokens_spent: int

    alert_threshold: float
    remaining: Decimal  # In the active mode (dollars or tokens)
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
    """Update budget limits and mode (GH#8215, GH#8997)."""

    budget_mode: Optional[str] = None  # "dollars" or "tokens"
    budget_limit: Optional[Decimal] = None  # For DOLLARS mode
    token_limit: Optional[int] = None  # For TOKENS mode
    alert_threshold: Optional[float] = None


def _build_response(row: LLCAgentBudget, remaining: Decimal, is_over: bool, alert: bool) -> BudgetResponse:
    """Build BudgetResponse with token support (GH#8997)."""
    return BudgetResponse(
        agent_id=row.agent_id,
        budget_mode=str(row.budget_mode),
        budget_limit=Decimal(str(row.budget_limit)),
        budget_spent=Decimal(str(row.budget_spent)),
        token_limit=int(row.token_limit) if row.token_limit is not None else None,
        tokens_spent=int(row.tokens_spent),
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
    """List all per-agent budget rows for a company (GH#8551, GH#8997)."""
    result = await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.company_id == company_id))
    rows = result.scalars().all()
    svc = BudgetService()
    out: List[Dict[str, Any]] = []
    for row in rows:
        remaining, is_over, alert = await svc.check_budget(session, row.agent_id)
        out.append(
            {
                "agent_id": row.agent_id,
                "budget_mode": str(row.budget_mode),
                "budget_limit": str(row.budget_limit),
                "budget_spent": str(row.budget_spent),
                "token_limit": int(row.token_limit) if row.token_limit is not None else None,
                "tokens_spent": int(row.tokens_spent),
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
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=402, detail="Internal server error") from exc
    return IngestResponse(cost=cost)


@router.patch("/{agent_id}/limit", response_model=BudgetResponse)
async def update_limit(
    agent_id: str,
    body: UpdateLimitRequest,
    session: AsyncSession = Depends(get_async_session),
) -> BudgetResponse:
    """Update budget limits and mode (GH#8215, GH#8997)."""
    result = await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == agent_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No budget row for agent {agent_id}")

    # GH#8462: pass Decimal directly — Pydantic already validates it as Decimal,
    # no str() conversion needed (which would silently coerce to TEXT in the ORM).
    # GH#8997: support budget_mode and token_limit updates.
    values: dict = {}
    if body.budget_mode is not None:
        if body.budget_mode not in ("dollars", "tokens"):
            raise HTTPException(status_code=400, detail="budget_mode must be 'dollars' or 'tokens'")
        values["budget_mode"] = body.budget_mode
    if body.budget_limit is not None:
        values["budget_limit"] = body.budget_limit
    if body.token_limit is not None:
        values["token_limit"] = body.token_limit
    if body.alert_threshold is not None:
        values["alert_threshold"] = body.alert_threshold

    if not values:
        raise HTTPException(status_code=400, detail="No fields to update")

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


# ---------------------------------------------------------------------------
# GET /companies/{company_id}/costs/by-agent-model — Haiku token dashboard
# (GH#8486 — item 4)
# ---------------------------------------------------------------------------


class AgentModelCostRow(BaseModel):
    """Per-agent + per-model token breakdown row."""

    agent_id: str
    agent_name: str
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cache_hit_rate: float
    cost_usd: str


@costs_by_model_router.get(
    "/{company_id}/costs/by-agent-model",
    response_model=List[AgentModelCostRow],
    summary="Token breakdown per agent+model with cache hit rate (GH#8486)",
)
async def costs_by_agent_model(
    company_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> List[AgentModelCostRow]:
    """Return token usage broken down by agent and model for a company.

    Required fields: agentId, agentName, model, inputTokens,
    cachedInputTokens, outputTokens, cacheHitRate.

    Cache hit rate = cachedInputTokens / totalInputTokens.  A low rate
    signals session churn — the agent is not benefiting from prompt caching.

    Data is sourced from ``agent_org_nodes`` (for model + name) joined to
    ``llc_heartbeat_runs`` (for token usage).  Rows without any heartbeat
    runs are included with zero token counts so the roster is always complete.

    Note: ``llc_heartbeat_runs`` does not yet have ``input_tokens`` /
    ``cached_input_tokens`` columns.  The query returns zeros for those until
    a future migration adds the columns.  The endpoint is intentionally
    available from day one so dashboards can start wiring up immediately.
    """
    result = await session.execute(
        text("""
            SELECT
                aon.agent_id,
                aon.name                                   AS agent_name,
                COALESCE(aon.model, 'claude-sonnet-4-6')   AS model,
                COALESCE(SUM(hr.tokens_in), 0)             AS input_tokens,
                0                                          AS cached_input_tokens,
                COALESCE(SUM(hr.tokens_out), 0)            AS output_tokens
            FROM agent_org_nodes aon
            LEFT JOIN llc_heartbeat_runs hr
                   ON hr.agent_id = aon.agent_id
            WHERE aon.company_id = :company_id
            GROUP BY aon.agent_id, aon.name, aon.model
            ORDER BY output_tokens DESC
        """),
        {"company_id": company_id},
    )
    rows = result.mappings().all()

    out: List[AgentModelCostRow] = []
    for row in rows:
        total_in = int(row["input_tokens"]) + int(row["cached_input_tokens"])
        cache_hit_rate = round(int(row["cached_input_tokens"]) / total_in, 4) if total_in > 0 else 0.0
        out.append(
            AgentModelCostRow(
                agent_id=row["agent_id"],
                agent_name=row["agent_name"],
                model=row["model"],
                input_tokens=int(row["input_tokens"]),
                cached_input_tokens=int(row["cached_input_tokens"]),
                output_tokens=int(row["output_tokens"]),
                cache_hit_rate=cache_hit_rate,
                cost_usd="0.00",  # populated by a future cost calculation pass
            )
        )
    return out
