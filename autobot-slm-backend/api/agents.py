# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Agents API Routes

API endpoints for managing AI agents with per-agent LLM configuration.
Related to Issue #760 Phase 2.
"""

import logging
from typing import Optional

from api.websocket import ws_manager
from config import settings
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query, status
from models.database import Agent
from models.schemas import (
    AgentCreateRequest,
    AgentListResponse,
    AgentLLMConfigWithKey,
    AgentResponse,
    AgentUpdateRequest,
)
from services.auth import get_current_user
from services.database import get_db
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"])


def _get_fernet() -> Fernet:
    """Get Fernet cipher for API key encryption/decryption."""
    if not settings.encryption_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Encryption key not configured",
        )
    return Fernet(settings.encryption_key.encode("utf-8"))


def _encrypt_api_key(api_key: str) -> str:
    """Encrypt API key for storage."""
    if not api_key:
        return ""
    cipher = _get_fernet()
    return cipher.encrypt(api_key.encode("utf-8")).decode("utf-8")


def _decrypt_api_key(encrypted_key: str) -> Optional[str]:
    """Decrypt API key from storage."""
    if not encrypted_key:
        return None
    try:
        cipher = _get_fernet()
        return cipher.decrypt(encrypted_key.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error("Failed to decrypt API key: %s", e)
        return None


@router.get("", response_model=AgentListResponse)
async def list_agents(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
) -> AgentListResponse:
    """List all agents with pagination and filtering."""
    query = select(Agent)

    if search:
        query = query.where(
            (Agent.name.ilike(f"%{search}%"))
            | (Agent.agent_id.ilike(f"%{search}%"))
            | (Agent.description.ilike(f"%{search}%"))
        )

    if is_active is not None:
        query = query.where(Agent.is_active == is_active)

    query = query.order_by(Agent.is_default.desc(), Agent.name)

    # Count total
    count_query = select(func.count(Agent.id))
    if search:
        count_query = count_query.where(
            (Agent.name.ilike(f"%{search}%"))
            | (Agent.agent_id.ilike(f"%{search}%"))
            | (Agent.description.ilike(f"%{search}%"))
        )
    if is_active is not None:
        count_query = count_query.where(Agent.is_active == is_active)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    agents = result.scalars().all()

    return AgentListResponse(
        agents=[AgentResponse.model_validate(a) for a in agents],
        total=total,
    )


@router.get("/default", response_model=AgentResponse)
async def get_default_agent(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AgentResponse:
    """Get the default agent."""
    result = await db.execute(
        select(Agent).where(Agent.is_default.is_(True), Agent.is_active.is_(True))
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No default agent configured",
        )

    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AgentResponse:
    """Get a specific agent by ID."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}/llm", response_model=AgentLLMConfigWithKey)
async def get_agent_llm_config(
    agent_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AgentLLMConfigWithKey:
    """Get LLM configuration for an agent with decrypted API key."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    # Decrypt API key
    api_key = None
    if agent.llm_api_key_encrypted:
        api_key = _decrypt_api_key(agent.llm_api_key_encrypted)

    return AgentLLMConfigWithKey(
        llm_provider=agent.llm_provider,
        llm_endpoint=agent.llm_endpoint,
        llm_model=agent.llm_model,
        llm_timeout=agent.llm_timeout,
        llm_temperature=agent.llm_temperature,
        llm_max_tokens=agent.llm_max_tokens,
        llm_api_key=api_key,
    )


async def _clear_default_agents(db: AsyncSession) -> None:
    """Helper for create_agent and update_agent. Ref: #1088."""
    current_default_result = await db.execute(
        select(Agent).where(Agent.is_default.is_(True))
    )
    for default_agent in current_default_result.scalars():
        default_agent.is_default = False


async def _broadcast_agent_event(event_type: str, agent: Agent) -> None:
    """Helper for create_agent and update_agent. Ref: #1088."""
    await ws_manager.broadcast(
        "events:global",
        {
            "type": event_type,
            "data": {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "llm_provider": agent.llm_provider,
                "is_default": agent.is_default,
            },
        },
    )


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    request: AgentCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AgentResponse:
    """Create a new agent."""
    result = await db.execute(select(Agent).where(Agent.agent_id == request.agent_id))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent with ID '{request.agent_id}' already exists",
        )

    if request.is_default:
        await _clear_default_agents(db)

    encrypted_key = (
        _encrypt_api_key(request.llm_api_key) if request.llm_api_key else None
    )

    agent = Agent(
        agent_id=request.agent_id,
        name=request.name,
        description=request.description,
        llm_provider=request.llm_provider,
        llm_endpoint=request.llm_endpoint,
        llm_model=request.llm_model,
        llm_api_key_encrypted=encrypted_key,
        llm_timeout=request.llm_timeout,
        llm_temperature=request.llm_temperature,
        llm_max_tokens=request.llm_max_tokens,
        is_default=request.is_default,
        is_active=request.is_active,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    logger.info(
        "Created agent %s (%s) with provider %s",
        agent.agent_id,
        agent.name,
        agent.llm_provider,
    )
    await _broadcast_agent_event("agent_created", agent)

    return AgentResponse.model_validate(agent)


def _apply_agent_update_fields(agent: Agent, request: AgentUpdateRequest) -> None:
    """Helper for update_agent. Ref: #1088."""
    if request.name is not None:
        agent.name = request.name
    if request.description is not None:
        agent.description = request.description
    if request.llm_provider is not None:
        agent.llm_provider = request.llm_provider
    if request.llm_endpoint is not None:
        agent.llm_endpoint = request.llm_endpoint
    if request.llm_model is not None:
        agent.llm_model = request.llm_model
    if request.llm_timeout is not None:
        agent.llm_timeout = request.llm_timeout
    if request.llm_temperature is not None:
        agent.llm_temperature = request.llm_temperature
    if request.llm_max_tokens is not None:
        agent.llm_max_tokens = request.llm_max_tokens
    if request.is_default is not None:
        agent.is_default = request.is_default
    if request.is_active is not None:
        agent.is_active = request.is_active
    if request.llm_api_key is not None:
        agent.llm_api_key_encrypted = _encrypt_api_key(request.llm_api_key)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    request: AgentUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AgentResponse:
    """Update an existing agent."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    if request.is_default is True and not agent.is_default:
        await _clear_default_agents(db)

    _apply_agent_update_fields(agent, request)

    await db.commit()
    await db.refresh(agent)

    logger.info("Updated agent %s (%s)", agent.agent_id, agent.name)
    await _broadcast_agent_event("agent_config_changed", agent)

    return AgentResponse.model_validate(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> None:
    """Delete an agent. Cannot delete the default agent."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    if agent.is_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the default agent",
        )

    await db.delete(agent)
    await db.commit()

    logger.info("Deleted agent %s (%s)", agent.agent_id, agent.name)

    # Broadcast agent deletion via WebSocket
    await ws_manager.broadcast(
        "events:global",
        {
            "type": "agent_deleted",
            "data": {
                "agent_id": agent.agent_id,
                "name": agent.name,
            },
        },
    )
