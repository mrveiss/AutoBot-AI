# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
External Agent Registry API (Issue #963).

Manages the registry of external A2A-compliant agents.

Routes (prefix /external-agents):
  GET    /cards                 All cards for enabled+verified agents (for router)
  POST   /                     Register new external agent
  GET    /                     List all agents
  GET    /{id}                  Agent detail + full card
  PUT    /{id}                  Update name/tags/enabled/ssl_verify/description
  DELETE /{id}                  Remove agent
  POST   /{id}/verify           Fetch card and mark verified
  POST   /{id}/refresh          Re-fetch card (async)

NOTE: /cards MUST be registered before /{id} to avoid path-parameter collision.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from models.database import ExternalAgent
from pydantic import BaseModel, Field
from services.auth import get_current_user
from services.database import get_db
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/external-agents", tags=["external-agents"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ExternalAgentCreate(BaseModel):
    name: str = Field(..., max_length=100)
    base_url: str = Field(..., description="Base URL of the external A2A agent")
    description: Optional[str] = None
    tags: List[str] = []
    enabled: bool = True
    ssl_verify: bool = True
    api_key: Optional[str] = Field(None, description="Bearer token (stored encrypted)")


class ExternalAgentUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    enabled: Optional[bool] = None
    ssl_verify: Optional[bool] = None
    api_key: Optional[str] = Field(None, description="Set to '' to clear api_key")


def _serialize(agent: ExternalAgent, include_card: bool = True) -> Dict[str, Any]:
    """Serialize an ExternalAgent ORM row to a response dict."""
    return {
        "id": agent.id,
        "name": agent.name,
        "base_url": agent.base_url,
        "description": agent.description,
        "tags": agent.tags or [],
        "enabled": agent.enabled,
        "ssl_verify": agent.ssl_verify,
        "has_api_key": bool(agent.api_key),
        "verified": agent.verified,
        "card_data": agent.card_data if include_card else None,
        "card_fetched_at": (
            agent.card_fetched_at.isoformat() if agent.card_fetched_at else None
        ),
        "card_error": agent.card_error,
        "skill_count": len((agent.card_data or {}).get("skills", [])),
        "created_by": agent.created_by,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


# ---------------------------------------------------------------------------
# GET /cards — must precede GET /{id}
# ---------------------------------------------------------------------------


@router.get("/cards")
async def list_agent_cards(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> List[Dict[str, Any]]:
    """
    Return Agent Cards for all enabled and verified external agents.

    Consumed by AutoBot's AgentRouter to include external agents in
    routing candidates.
    """
    result = await db.execute(
        select(ExternalAgent).where(
            ExternalAgent.enabled.is_(True),
            ExternalAgent.verified.is_(True),
            ExternalAgent.card_data.isnot(None),
        )
    )
    agents = result.scalars().all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "base_url": a.base_url,
            "card": a.card_data,
        }
        for a in agents
    ]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_agent(
    body: ExternalAgentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> Dict[str, Any]:
    """Register a new external A2A agent."""
    existing = await db.execute(
        select(ExternalAgent).where(ExternalAgent.base_url == body.base_url)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent with base_url '{body.base_url}' already registered",
        )

    encrypted_key: Optional[str] = None
    if body.api_key:
        from services.encryption import encrypt_data

        encrypted_key = encrypt_data(body.api_key)

    agent = ExternalAgent(
        name=body.name,
        base_url=body.base_url.rstrip("/"),
        description=body.description,
        tags=body.tags,
        enabled=body.enabled,
        ssl_verify=body.ssl_verify,
        api_key=encrypted_key,
        created_by=current_user.get("username"),
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    logger.info("External agent registered: %s (%s)", agent.name, agent.base_url)
    return _serialize(agent)


@router.get("")
async def list_agents(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> List[Dict[str, Any]]:
    """List all registered external agents (summary, no full card data)."""
    result = await db.execute(select(ExternalAgent).order_by(ExternalAgent.name))
    agents = result.scalars().all()
    return [_serialize(a, include_card=False) for a in agents]


@router.get("/{agent_id}")
async def get_agent(
    agent_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> Dict[str, Any]:
    """Return full detail including cached Agent Card."""
    result = await db.execute(select(ExternalAgent).where(ExternalAgent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    return _serialize(agent)


@router.put("/{agent_id}")
async def update_agent(
    agent_id: int,
    body: ExternalAgentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> Dict[str, Any]:
    """Update name, description, tags, enabled, ssl_verify, or api_key."""
    result = await db.execute(select(ExternalAgent).where(ExternalAgent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )

    if body.name is not None:
        agent.name = body.name
    if body.description is not None:
        agent.description = body.description
    if body.tags is not None:
        agent.tags = body.tags
    if body.enabled is not None:
        agent.enabled = body.enabled
    if body.ssl_verify is not None:
        agent.ssl_verify = body.ssl_verify
    if body.api_key is not None:
        if body.api_key == "":
            agent.api_key = None
        else:
            from services.encryption import encrypt_data

            agent.api_key = encrypt_data(body.api_key)

    agent.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(agent)
    return _serialize(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> None:
    """Remove an external agent from the registry."""
    result = await db.execute(select(ExternalAgent).where(ExternalAgent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    await db.delete(agent)
    await db.commit()
    logger.info("External agent deleted: id=%s name=%s", agent_id, agent.name)


# ---------------------------------------------------------------------------
# Verification and refresh
# ---------------------------------------------------------------------------


@router.post("/{agent_id}/verify")
async def verify_agent(
    agent_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> Dict[str, Any]:
    """
    Fetch the agent's /.well-known/agent.json and mark as verified on success.

    Synchronous — waits for the fetch to complete and returns the result.
    """
    result = await db.execute(select(ExternalAgent).where(ExternalAgent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )

    from services.a2a_card_fetcher import fetch_card_for_external

    card = await fetch_card_for_external(agent_id)

    # Reload to get updated values after fetch
    await db.refresh(agent)
    return {
        **_serialize(agent),
        "success": card is not None,
    }


@router.post("/{agent_id}/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_agent_card(
    agent_id: int,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> Dict[str, Any]:
    """
    Queue a background card re-fetch.

    Returns 202 immediately. Poll GET /{id} for updated card_data.
    """
    result = await db.execute(select(ExternalAgent).where(ExternalAgent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )

    from services.a2a_card_fetcher import fetch_card_for_external

    background_tasks.add_task(fetch_card_for_external, agent_id)
    logger.info("External agent card refresh queued: id=%s", agent_id)
    return {"id": agent_id, "status": "refresh_queued"}
