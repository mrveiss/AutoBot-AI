# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Agent-hire API (GH#8487).

Routes:
  POST /agent-hires   — create an assistant agent for a given senior agent,
                        auto-resolving the cheap model for the senior's provider.
  GET  /agent-hires   — list hire records for the org.

When ``assistantFor`` is supplied in the request body the hire endpoint:
  1. Looks up the senior agent's adapterConfig to detect its provider.
  2. Resolves the cheapest assistant model via ModelTierService (tier map in
     llc/config/model-tiers.yml, company overrides, per-agent overrides).
  3. Records the hire with the resolved model in ``hire_metadata``.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from llc.services.model_tiers import get_model_tier_service
from user_management.database import get_async_session
from user_management.services import TenantContext

logger = get_logger(__name__)

router = APIRouter(prefix="/agent-hires", tags=["llc-agent-hires"])

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AgentHireCreate(BaseModel):
    """Request body for POST /agent-hires."""

    assistant_for: Optional[str] = None
    """ID of the senior agent for which to create a cheap assistant.

    When set, the assistant model is auto-resolved from the senior agent's
    provider via ModelTierService.
    """

    adapter_config: Optional[Dict[str, Any]] = None
    """Explicit adapter configuration for the new assistant agent.

    Optional — if omitted the config is derived from the senior agent with the
    assistant model substituted in.
    """

    company_id: Optional[uuid.UUID] = None
    """Override company scope; defaults to the caller's org."""


class AgentHireRead(BaseModel):
    """Response schema for a created / listed hire."""

    id: uuid.UUID
    company_id: uuid.UUID
    senior_agent_id: Optional[str]
    assistant_agent_id: str
    resolved_provider: Optional[str]
    resolved_model: Optional[str]
    hire_metadata: Dict[str, Any]


# ---------------------------------------------------------------------------
# Route implementations
# ---------------------------------------------------------------------------


async def _fetch_agent_config(
    session: AsyncSession,
    agent_id: str,
    company_id: str,
) -> Optional[Dict[str, Any]]:
    """Return the adapter_config JSON for *agent_id* in *company_id*, or None."""
    try:
        result = await session.execute(
            text(
                """
                SELECT adapter_config
                FROM agent_org_nodes
                WHERE agent_id = :agent_id
                  AND company_id = :company_id
                LIMIT 1
                """
            ),
            {"agent_id": agent_id, "company_id": company_id},
        )
        row = result.fetchone()
        if row and row[0]:
            return dict(row[0]) if isinstance(row[0], dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch adapter_config for agent %r: %s", agent_id, exc)
    return None


async def _fetch_company_model_overrides(
    session: AsyncSession,
    company_id: str,
) -> Optional[Dict[str, Any]]:
    """Return model_tier_overrides JSON stored in the organization row, or None."""
    try:
        result = await session.execute(
            text(
                """
                SELECT settings->'model_tier_overrides'
                FROM organizations
                WHERE id = :company_id
                LIMIT 1
                """
            ),
            {"company_id": company_id},
        )
        row = result.fetchone()
        if row and row[0]:
            return dict(row[0]) if isinstance(row[0], dict) else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not fetch company model_tier_overrides for %r: %s", company_id, exc)
    return None


@router.post("", response_model=AgentHireRead, status_code=201)
async def create_agent_hire(
    body: AgentHireCreate,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(lambda: None),  # injected when middleware present
) -> AgentHireRead:
    """Create an assistant agent for a senior agent with auto-resolved model.

    ``assistantFor`` triggers provider detection → model tier resolution →
    hire record creation.  If the senior agent's provider cannot be detected the
    endpoint still succeeds but ``resolved_model`` will be ``null``.
    """
    # Determine effective company_id
    effective_company_id = str(body.company_id) if body.company_id else (
        str(ctx.org_id) if ctx else None
    )
    if not effective_company_id:
        raise HTTPException(status_code=400, detail="company_id is required")

    svc = get_model_tier_service()
    senior_adapter_cfg: Optional[Dict[str, Any]] = None
    resolved_provider: Optional[str] = None
    resolved_model: Optional[str] = None

    if body.assistant_for:
        # Fetch the senior agent's adapter config from the DB
        senior_adapter_cfg = await _fetch_agent_config(session, body.assistant_for, effective_company_id)
        if senior_adapter_cfg is None:
            # Gracefully continue — caller may be seeding agents pre-DB
            logger.info(
                "Senior agent %r not found in DB; will attempt model resolution from request body",
                body.assistant_for,
            )
            senior_adapter_cfg = body.adapter_config or {}

        company_overrides = await _fetch_company_model_overrides(session, effective_company_id)

        resolved_model = svc.resolve_assistant_model(
            senior_agent_adapter_config=senior_adapter_cfg,
            company_overrides=company_overrides,
        )
        if senior_adapter_cfg:
            resolved_provider = svc.detect_provider(senior_adapter_cfg.get("model", ""))

    # Build the assistant adapter_config by inheriting from the senior and
    # substituting the resolved cheap model.
    assistant_adapter_cfg: Dict[str, Any] = dict(senior_adapter_cfg or body.adapter_config or {})
    if resolved_model:
        assistant_adapter_cfg["model"] = resolved_model

    assistant_agent_id = f"assistant-{body.assistant_for or 'standalone'}-{uuid.uuid4().hex[:8]}"

    hire_id = uuid.uuid4()
    hire_metadata: Dict[str, Any] = {
        "adapter_config": assistant_adapter_cfg,
        "creation_strategy": "auto_resolved" if resolved_model else "manual",
    }

    # Persist hire record — table may not exist yet; gracefully continue.
    try:
        await session.execute(
            text(
                """
                INSERT INTO llc_agent_hires
                    (id, company_id, senior_agent_id, assistant_agent_id,
                     resolved_provider, resolved_model, hire_metadata)
                VALUES
                    (:id, :company_id, :senior_agent_id, :assistant_agent_id,
                     :resolved_provider, :resolved_model, :hire_metadata::jsonb)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": str(hire_id),
                "company_id": effective_company_id,
                "senior_agent_id": body.assistant_for,
                "assistant_agent_id": assistant_agent_id,
                "resolved_provider": resolved_provider,
                "resolved_model": resolved_model,
                "hire_metadata": __import__("json").dumps(hire_metadata),
            },
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not persist hire record (table may not exist): %s", exc)
        await session.rollback()

    return AgentHireRead(
        id=hire_id,
        company_id=uuid.UUID(effective_company_id),
        senior_agent_id=body.assistant_for,
        assistant_agent_id=assistant_agent_id,
        resolved_provider=resolved_provider,
        resolved_model=resolved_model,
        hire_metadata=hire_metadata,
    )


@router.get("", response_model=List[AgentHireRead])
async def list_agent_hires(
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(lambda: None),
) -> List[AgentHireRead]:
    """List agent hire records for the caller's org."""
    if not ctx:
        return []
    effective_company_id = str(ctx.org_id)
    try:
        result = await session.execute(
            text(
                """
                SELECT id, company_id, senior_agent_id, assistant_agent_id,
                       resolved_provider, resolved_model, hire_metadata
                FROM llc_agent_hires
                WHERE company_id = :company_id
                ORDER BY created_at DESC
                LIMIT 200
                """
            ),
            {"company_id": effective_company_id},
        )
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("llc_agent_hires table not available: %s", exc)
        return []

    return [
        AgentHireRead(
            id=uuid.UUID(str(r[0])),
            company_id=uuid.UUID(str(r[1])),
            senior_agent_id=r[2],
            assistant_agent_id=r[3],
            resolved_provider=r[4],
            resolved_model=r[5],
            hire_metadata=dict(r[6]) if r[6] else {},
        )
        for r in rows
    ]
