# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Provider-normalised cost reporting endpoints (GH#8487).

Routes:
  GET /costs/by-agent-model   — normalised token usage per agent/model across
                                Anthropic, OpenAI, Google, and other providers.
  GET /costs/quota-windows    — provider quota headroom per configured provider.

Token field normalisation
-------------------------
Each provider uses different field names in usage metadata:

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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from llc.services.model_tiers import get_model_tier_service
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
    ctx: TenantContext = Depends(lambda: None),
) -> List[AgentModelCost]:
    """Return normalised token usage per agent/model pair.

    Aggregates rows from ``llc_cost_events`` and normalises token field names
    across Anthropic, OpenAI, and Google so callers receive a consistent schema.
    ``cachedInputTokens`` is ``0`` for providers without cache hit reporting.
    """
    effective_company_id = company_id or (str(ctx.org_id) if ctx else None)
    if not effective_company_id:
        return []

    svc = get_model_tier_service()

    try:
        result = await session.execute(
            text(
                """
                SELECT
                    agent_id,
                    COALESCE(agent_id, 'unknown') AS agent_name,
                    model,
                    COALESCE(SUM((usage_metadata->>'input_tokens')::int), 0)
                        + COALESCE(SUM((usage_metadata->>'prompt_tokens')::int), 0)
                        + COALESCE(SUM((usage_metadata->>'prompt_token_count')::int), 0)
                        AS raw_input,
                    COALESCE(SUM((usage_metadata->>'cache_read_input_tokens')::int), 0)
                        AS raw_cached,
                    COALESCE(SUM((usage_metadata->>'output_tokens')::int), 0)
                        + COALESCE(SUM((usage_metadata->>'completion_tokens')::int), 0)
                        + COALESCE(SUM((usage_metadata->>'candidates_token_count')::int), 0)
                        AS raw_output,
                    provider
                FROM llc_cost_events
                WHERE company_id = :company_id
                GROUP BY agent_id, model, provider
                ORDER BY agent_id, model
                """
            ),
            {"company_id": effective_company_id},
        )
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("llc_cost_events not available: %s", exc)
        rows = []

    out: List[AgentModelCost] = []
    for row in rows:
        agent_id, agent_name, model, raw_input, raw_cached, raw_output, db_provider = row
        provider = db_provider or svc.detect_provider(model or "")
        out.append(
            AgentModelCost(
                agent_id=str(agent_id),
                agent_name=str(agent_name),
                provider=provider,
                model=str(model or ""),
                input_tokens=int(raw_input or 0),
                cached_input_tokens=int(raw_cached or 0),
                output_tokens=int(raw_output or 0),
            )
        )
    return out


@router.get("/quota-windows", response_model=List[QuotaWindow])
async def quota_windows(
    company_id: Optional[str] = Query(None, description="Filter by company UUID"),
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(lambda: None),
) -> List[QuotaWindow]:
    """Return provider quota window structures for all configured providers.

    Each entry describes the rate-limit windows applicable to the provider
    (e.g. RPM + TPM for OpenAI; 5-hour + 7-day output token windows for
    Anthropic).  Actual headroom values require provider API key configuration
    and are populated by the quota monitor (phase 3).
    """
    effective_company_id = company_id or (str(ctx.org_id) if ctx else None)
    svc = get_model_tier_service()

    # Determine which providers are actively used by looking at cost events
    active_providers: set[str] = set()
    if effective_company_id:
        try:
            result = await session.execute(
                text(
                    """
                    SELECT DISTINCT provider
                    FROM llc_cost_events
                    WHERE company_id = :company_id
                      AND provider IS NOT NULL
                    """
                ),
                {"company_id": effective_company_id},
            )
            active_providers = {row[0] for row in result.fetchall() if row[0]}
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not query active providers: %s", exc)

    # Also include providers from the platform tier map so the endpoint is
    # useful even before any cost events have been ingested.
    tier_map = svc.get_tier_map()
    all_providers = active_providers | set(tier_map.keys())

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
