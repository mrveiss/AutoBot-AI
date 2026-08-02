# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provider-normalised cost reporting endpoints (GH#8487).

Routes:
  GET /costs/by-agent-model   — lifetime token totals per agent, sourced from
                                llc_agent_budgets (GH#13067; see that route's
                                docstring — no per-model/provider breakdown
                                exists yet).
  GET /costs/quota-windows    — provider quota headroom per configured provider.

Token field normalisation
-------------------------
``_normalise_usage`` below maps each provider's raw usage-metadata field names
to the (input, cached, output) triple. It is kept for the per-model/provider
breakdown this module was originally specified to provide (GH#8215) once a
real per-event cost log exists; nothing calls it today (GH#13067).

  Provider   | input field           | cached field              | output field
  -----------|-----------------------|---------------------------|------------------
  Anthropic  | input_tokens          | cache_read_input_tokens   | output_tokens
  OpenAI     | prompt_tokens         | — (no public cache field) | completion_tokens
  Google     | prompt_token_count    | — (no public cache field) | candidates_token_count
  Mistral    | prompt_tokens         | — (no public cache field) | completion_tokens
  Groq       | prompt_tokens         | — (no public cache field) | completion_tokens

``cachedInputTokens`` is returned as 0 for providers that do not expose cache
hit counts (OpenAI, Google, Mistral, Groq).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.logging_manager import get_logger
from llc.deps import assert_company_access
from llc.models.budget import LLCAgentBudget
from llc.services.model_tiers import get_model_tier_service
from models.agent_org import AgentOrgNode
from user_management.database import get_async_session
from user_management.services import TenantContext

logger = get_logger(__name__)

router = APIRouter(prefix="/costs", tags=["llc-costs"])

# ---------------------------------------------------------------------------
# Provider token field normalisation
# ---------------------------------------------------------------------------

# Maps provider key → (input_field, cached_field_or_None, output_field)
_PROVIDER_TOKEN_FIELDS: Dict[str, tuple[str, Optional[str], str]] = {
    "anthropic": ("input_tokens", "cache_read_input_tokens", "output_tokens"),
    "openai": ("prompt_tokens", None, "completion_tokens"),
    "google": ("prompt_token_count", None, "candidates_token_count"),
    "mistral": ("prompt_tokens", None, "completion_tokens"),
    "groq": ("prompt_tokens", None, "completion_tokens"),
    "together": ("prompt_tokens", None, "completion_tokens"),
}

# Quota window structures per provider
_PROVIDER_QUOTA_STRUCTURE: Dict[str, Dict[str, Any]] = {
    "anthropic": {
        "windows": ["5h_output_tokens", "7d_output_tokens"],
        "description": "5-hour and 7-day output token windows per model tier",
    },
    "openai": {
        "windows": ["rpm", "tpm", "daily_tokens"],
        "description": "Requests-per-minute, tokens-per-minute, and daily token limits",
    },
    "google": {
        "windows": ["rpm", "daily_requests"],
        "description": "Requests-per-minute and daily quota per model",
    },
    "mistral": {
        "windows": ["rpm", "monthly_tokens"],
        "description": "Requests-per-minute and monthly token budget",
    },
    "groq": {
        "windows": ["rpm", "tpm"],
        "description": "Requests-per-minute and tokens-per-minute",
    },
}


def _normalise_usage(usage: Dict[str, Any], provider: str) -> tuple[int, int, int]:
    """Return (input_tokens, cached_input_tokens, output_tokens) from raw usage dict.

    Uses provider-specific field names; falls back to 0 for unknown fields.
    """
    if not usage:
        return 0, 0, 0

    fields = _PROVIDER_TOKEN_FIELDS.get(provider, ("prompt_tokens", None, "completion_tokens"))
    input_field, cached_field, output_field = fields

    input_tokens = int(usage.get(input_field, 0) or 0)
    cached_tokens = int(usage.get(cached_field, 0) or 0) if cached_field else 0
    output_tokens = int(usage.get(output_field, 0) or 0)

    return input_tokens, cached_tokens, output_tokens


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class AgentModelCost(BaseModel):
    """Normalised token usage for one agent/model pair."""

    agent_id: str
    agent_name: str
    provider: Optional[str]
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


class QuotaWindow(BaseModel):
    """Quota headroom for one provider."""

    provider: str
    windows: List[str]
    description: str
    note: str = "Headroom values require provider API key configuration to populate."


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/by-agent-model", response_model=List[AgentModelCost])
async def costs_by_agent_model(
    company_id: Optional[str] = Query(None, description="Filter by company UUID"),
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[AgentModelCost]:
    """Return lifetime token totals per agent for a company.

    Originally specified against ``llc_cost_events`` (GH#8215's per-event log
    with model/provider columns), a table that was never migrated — confirmed
    absent from every migration tree, so this endpoint always raised
    ``UndefinedTable`` and silently returned ``[]`` (GH#13067). The actual
    writer, ``BudgetService.ingest_cost_event``, only maintains a lifetime
    aggregate on ``llc_agent_budgets`` (no per-model dimension, no timestamp),
    so each row here is one lifetime token total per agent with
    ``model="unknown"`` rather than a real per-model/time-windowed breakdown.
    ``llc/services/agent_scorecard.py`` hit the identical gap and made the
    same sourcing choice for spend.
    """
    if company_id:
        assert_company_access(ctx, company_id)
    effective_company_id = company_id or str(ctx.org_id)
    if not effective_company_id:
        return []

    result = await session.execute(
        select(LLCAgentBudget, AgentOrgNode.name)
        .outerjoin(AgentOrgNode, AgentOrgNode.agent_id == LLCAgentBudget.agent_id)
        .where(LLCAgentBudget.company_id == effective_company_id)
        .order_by(LLCAgentBudget.agent_id)
    )

    return [
        AgentModelCost(
            agent_id=budget.agent_id,
            agent_name=agent_name or budget.agent_id,
            provider=None,
            model="unknown",
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=int(budget.tokens_spent),
        )
        for budget, agent_name in result.all()
    ]


@router.get("/quota-windows", response_model=List[QuotaWindow])
async def quota_windows(
    company_id: Optional[str] = Query(None, description="Filter by company UUID"),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[QuotaWindow]:
    """Return provider quota window structures for all configured providers.

    Each entry describes the rate-limit windows applicable to the provider
    (e.g. RPM + TPM for OpenAI; 5-hour + 7-day output token windows for
    Anthropic).  Actual headroom values require provider API key configuration
    and are populated by the quota monitor (phase 3).
    """
    if company_id:
        assert_company_access(ctx, company_id)
    svc = get_model_tier_service()

    # "Actively used" providers were meant to come from llc_cost_events
    # (GH#8487), but that table was never migrated (GH#13067) and its real
    # replacement, llc_agent_budgets, carries no provider column — there is
    # currently no per-company usage signal to source this from, so the
    # response is the platform tier map only.
    tier_map = svc.get_tier_map()
    all_providers = set(tier_map.keys())

    return [
        QuotaWindow(
            provider=p,
            windows=_PROVIDER_QUOTA_STRUCTURE.get(p, {}).get("windows", ["rpm"]),
            description=_PROVIDER_QUOTA_STRUCTURE.get(p, {}).get(
                "description", f"Rate limit windows for provider {p!r}"
            ),
        )
        for p in sorted(all_providers)
        if p in _PROVIDER_QUOTA_STRUCTURE or p in tier_map
    ]
