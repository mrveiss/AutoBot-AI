# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC per-agent budget API routes (GH#8215)."""

import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, get_tenant_context, require_org_context
from autobot_shared.logging_manager import get_logger
from llc.deps import assert_company_access, load_authorized
from llc.exceptions import BudgetExhausted
from llc.models.budget import LLCAgentBudget
from llc.services.budget import BudgetService
from models.agent_org import AgentOrgNode
from user_management.database import get_async_session
from user_management.services import TenantContext

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


class ProvisionRequest(BaseModel):
    """Request body for POST /budget/{agent_id} (GH#9901).

    budget_limit is optional — omitting it uses LLC_DEFAULT_BUDGET_LIMIT (default $10).
    company_id is derived from agent_org_nodes to prevent cross-company row insertion.
    """

    budget_limit: Optional[Decimal] = Field(None, gt=0, lt=Decimal("1000000000"))


def _derive_status(row: LLCAgentBudget) -> tuple:
    """Compute (remaining, is_over, alert_triggered) from a budget row (GH#8997).

    Centralises the spend/limit/threshold arithmetic used in every read path.
    Returns a plain tuple so callers can unpack directly.
    """
    budget_mode = str(row.budget_mode)
    spent = Decimal(str(row.budget_spent))
    limit = Decimal(str(row.budget_limit))
    threshold = Decimal(str(row.alert_threshold))
    tokens_spent = int(row.tokens_spent)
    token_limit = int(row.token_limit) if row.token_limit is not None else None

    if budget_mode == "tokens" and token_limit is not None:
        remaining = Decimal(str(token_limit - tokens_spent))
        is_over = tokens_spent > token_limit
        alert = token_limit > 0 and tokens_spent / token_limit >= threshold
    else:
        remaining = limit - spent
        is_over = spent > limit
        alert = limit > Decimal("0") and spent / limit >= threshold

    return remaining, is_over, alert


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


@router.post("/{agent_id}", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def provision_budget(
    agent_id: str,
    body: ProvisionRequest,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
) -> BudgetResponse:
    """Provision a default budget row for an agent (GH#9901).

    Returns 201 on creation, 409 if a row already exists.
    Returns 404 if the agent does not exist in agent_org_nodes, or belongs to
    a different tenant (GH#12136).
    company_id is derived from agent_org_nodes — callers cannot scope rows
    to arbitrary companies.
    """
    # Validate agent exists and derive company_id in a single query.
    agent_row = await session.execute(
        text("SELECT company_id FROM agent_org_nodes WHERE agent_id = :agent_id LIMIT 1"),
        {"agent_id": agent_id},
    )
    agent_record = agent_row.fetchone()
    if agent_record is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")

    # str(uuid.UUID(...)) canonicalises to the dashed lower-case form regardless
    # of how the raw text() query returns the UUID column across dialects
    # (GH#12136 — needed for the tenant-match comparison below).
    company_id = str(uuid.UUID(str(agent_record[0])))
    assert_company_access(ctx, company_id)

    svc = BudgetService()
    row, created = await svc.provision_budget(session, agent_id, company_id, body.budget_limit)
    if not created:
        raise HTTPException(
            status_code=409,
            detail=f"Budget row already exists for agent {agent_id}",
        )

    remaining, is_over, alert = _derive_status(row)
    return _build_response(row, remaining, is_over, alert)


@router.get("", response_model=List[Dict[str, Any]])
async def list_budgets(
    company_id: str = Query(..., description="Filter by company UUID"),
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[Dict[str, Any]]:
    """List all per-agent budget rows for a company (GH#8551, GH#8997)."""
    assert_company_access(ctx, company_id)
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
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
) -> BudgetResponse:
    # GH#8461: single SELECT — fetch the row directly and compute derived fields
    # here rather than calling check_budget() (which does its own SELECT) then
    # re-fetching the same row.
    row = await load_authorized(
        session,
        LLCAgentBudget,
        agent_id,
        ctx,
        id_attr="agent_id",
        not_found_detail=f"No budget row for agent {agent_id}",
    )

    remaining, is_over, alert = _derive_status(row)
    return _build_response(row, remaining, is_over, alert)


@router.post("/{agent_id}/ingest", response_model=IngestResponse)
async def ingest_cost(
    agent_id: str,
    body: IngestRequest,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
) -> IngestResponse:
    await load_authorized(
        session,
        LLCAgentBudget,
        agent_id,
        ctx,
        id_attr="agent_id",
        not_found_detail=f"No budget row for agent {agent_id}",
    )
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
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
) -> BudgetResponse:
    """Update budget limits and mode (GH#8215, GH#8997)."""
    row = await load_authorized(
        session,
        LLCAgentBudget,
        agent_id,
        ctx,
        id_attr="agent_id",
        not_found_detail=f"No budget row for agent {agent_id}",
    )

    # GH#8462: pass Decimal directly — Pydantic already validates it as Decimal,
    # no str() conversion needed (which would silently coerce to TEXT in the ORM).
    # GH#8997: support budget_mode and token_limit updates.
    # Validate mode-appropriate fields (GH#8997 "not both"):
    # - Setting token_limit while explicitly targeting dollars mode is rejected.
    # - Setting budget_limit while explicitly targeting tokens mode is rejected.
    effective_mode = body.budget_mode if body.budget_mode is not None else str(row.budget_mode)
    if body.budget_mode is not None and body.budget_mode not in ("dollars", "tokens"):
        raise HTTPException(status_code=400, detail="budget_mode must be 'dollars' or 'tokens'")
    if effective_mode == "dollars" and body.token_limit is not None:
        raise HTTPException(
            status_code=400,
            detail="token_limit cannot be set when budget_mode is 'dollars'",
        )
    # Asymmetry is deliberate: budget_limit on a row ALREADY in tokens mode is
    # allowed — it adjusts the dollar fallback used when token_limit is unset
    # (see watchdog/check_budget fallback semantics). Only the explicit switch
    # to tokens mode rejects a simultaneous budget_limit.
    if effective_mode == "tokens" and body.budget_limit is not None and body.budget_mode == "tokens":
        raise HTTPException(
            status_code=400,
            detail="budget_limit cannot be set when switching to budget_mode 'tokens'; set token_limit instead",
        )
    values: dict = {}
    if body.budget_mode is not None:
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

    # Drop the tracker cache so readers (watchdog, check_budget) see the new
    # mode/limit immediately instead of the pre-PATCH state for up to its TTL,
    # and derive the response from the freshly refreshed row.
    await BudgetService.invalidate_cache(agent_id)
    remaining, is_over, alert = _derive_status(row)
    return _build_response(row, remaining, is_over, alert)


# ---------------------------------------------------------------------------
# /cost-events — CostDashboard list endpoint (GH#8551)
# ---------------------------------------------------------------------------


@cost_events_router.get("", response_model=List[Dict[str, Any]])
async def list_cost_events(
    company_id: str = Query(..., description="Filter by company UUID"),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[Dict[str, Any]]:
    """Return per-agent budget spend summary as cost events (GH#8551).

    Returns one entry per agent with non-zero spend in the given company.
    A dedicated cost-event store is not yet implemented; this derives the
    data from LLCAgentBudget rows.
    """
    assert_company_access(ctx, company_id)
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
    """Per-agent + per-model token breakdown row.

    Mirrors ``llc/api/costs.py``'s ``AgentModelCost`` (GH#13067): this
    endpoint previously raw-SELECTed ``hr.tokens_in`` / ``hr.tokens_out`` from
    ``llc_heartbeat_runs``, columns that never existed on that model
    (GH#13330 — every call 500'd).  The only real per-agent token source is
    ``llc_agent_budgets.tokens_spent`` — a single combined
    ``tokens_in + tokens_out`` lifetime counter (``llc/services/budget.py``'s
    ``ingest_cost_event``), with no per-model dimension and no input/output
    split.  ``input_tokens`` / ``cached_input_tokens`` / ``output_tokens``
    stay ``0`` rather than putting the combined total under
    ``output_tokens`` — the first #13067 attempt did exactly that and applied
    output-rate pricing to input tokens (3-5x over).  The real number is
    reported only in ``total_tokens``.  ``cache_hit_rate`` has no source at
    all — no per-model cache-read counter exists anywhere in the schema — so
    it is ``None`` rather than a fabricated value.
    """

    agent_id: str
    agent_name: str
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_tokens: int
    cache_hit_rate: Optional[float] = None
    cost_usd: str


@costs_by_model_router.get(
    "/{company_id}/costs/by-agent-model",
    response_model=List[AgentModelCostRow],
    summary="Token breakdown per agent+model with cache hit rate (GH#8486)",
)
async def costs_by_agent_model(
    company_id: str,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[AgentModelCostRow]:
    """Return lifetime token totals per agent for a company (GH#13330).

    Sourced from ``llc_agent_budgets`` — the table ``BudgetService.
    ingest_cost_event`` (the actual writer) maintains — enriched with the
    display name from ``agent_org_nodes`` when the agent is registered there.
    ``model`` is always ``"unknown"`` and ``input_tokens`` /
    ``cached_input_tokens`` / ``output_tokens`` / ``cache_hit_rate`` cannot be
    populated honestly (see ``AgentModelCostRow`` docstring); the real spend
    signal is ``total_tokens`` and ``cost_usd``. Matches ``llc/api/costs.py``'s
    ``/costs/by-agent-model`` sibling endpoint, fixed for the identical gap
    in GH#13067.
    """
    assert_company_access(ctx, company_id)
    result = await session.execute(
        select(LLCAgentBudget, AgentOrgNode.name)
        .outerjoin(AgentOrgNode, AgentOrgNode.agent_id == LLCAgentBudget.agent_id)
        .where(LLCAgentBudget.company_id == company_id)
        .order_by(LLCAgentBudget.agent_id)
    )

    return [
        AgentModelCostRow(
            agent_id=budget.agent_id,
            agent_name=agent_name or budget.agent_id,
            model="unknown",
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            total_tokens=int(budget.tokens_spent),
            cache_hit_rate=None,
            cost_usd=str(budget.budget_spent),
        )
        for budget, agent_name in result.all()
    ]
