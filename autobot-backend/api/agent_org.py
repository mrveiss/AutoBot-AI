# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Org API (#1405)

Endpoints for agent organizational hierarchy: org tree, chain of command,
direct reports, and org metadata updates with cycle detection.
"""

import logging
from typing import Any, Dict, List, Optional

from api.user_management.dependencies import get_db_session
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from services.agent_org_service import AgentOrgService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter()


# -- Schemas ---------------------------------------------------------------


class OrgNodeResponse(BaseModel):
    """Single node in the org tree response (#1405)."""

    agent_id: str
    name: str
    org_role: str
    title: Optional[str] = None
    capabilities: Optional[str] = None
    direct_reports_count: int = 0
    children: List["OrgNodeResponse"] = Field(default_factory=list)


OrgNodeResponse.model_rebuild()


class AgentSummary(BaseModel):
    """Compact agent summary used in chain of command (#1405)."""

    agent_id: str
    name: str
    org_role: str
    title: Optional[str] = None


class ChainOfCommandResponse(BaseModel):
    """Ordered list from agent to org root (#1405)."""

    chain: List[AgentSummary]


class UpdateOrgRequest(BaseModel):
    """Request body for PATCH /agents/{agent_id}/org (#1405)."""

    reports_to: Optional[str] = Field(
        default=None,
        description="agent_id of the new manager, or null to clear",
    )
    org_role: Optional[str] = Field(
        default=None,
        description="One of: manager, coordinator, specialist, worker",
    )
    title: Optional[str] = Field(default=None, description="Human-readable job title")
    capabilities: Optional[str] = Field(
        default=None, description="Free-text capability description"
    )


class UpsertOrgRequest(BaseModel):
    """Request body for PUT /agents/{agent_id}/org (#1405)."""

    name: str
    org_role: str = "worker"
    reports_to: Optional[str] = None
    title: Optional[str] = None
    capabilities: Optional[str] = None


# -- Endpoints -------------------------------------------------------------


@router.get(
    "/org",
    response_model=List[OrgNodeResponse],
    tags=["agent-org"],
)
async def get_org_tree(
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """
    Return the full org tree from root agents (#1405).

    Each node contains nested children recursively.
    """
    svc = AgentOrgService(session)
    return await svc.get_org_tree()


@router.get(
    "/{agent_id}/chain",
    response_model=ChainOfCommandResponse,
    tags=["agent-org"],
)
async def get_chain_of_command(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ChainOfCommandResponse:
    """
    Return chain of command from agent_id up to org root (#1405).

    First entry is the agent itself; last is the root manager.
    """
    svc = AgentOrgService(session)
    try:
        chain = await svc.get_chain_of_command(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return ChainOfCommandResponse(chain=[AgentSummary(**item) for item in chain])


@router.get(
    "/{agent_id}/reports",
    response_model=List[AgentSummary],
    tags=["agent-org"],
)
async def get_direct_reports(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Return agents that directly report to agent_id (#1405)."""
    svc = AgentOrgService(session)
    return await svc.get_direct_reports(agent_id)


@router.patch(
    "/{agent_id}/org",
    response_model=AgentSummary,
    tags=["agent-org"],
)
async def update_agent_org(
    agent_id: str,
    body: UpdateOrgRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AgentSummary:
    """
    Update reporting line, role, or title for an agent (#1405).

    Returns 400 if the new reporting line would create a cycle.
    Returns 404 if the agent is not registered in the org hierarchy.
    """
    svc = AgentOrgService(session)
    try:
        node = await svc.update_reporting_line(
            agent_id=agent_id,
            new_manager_id=body.reports_to,
            org_role=body.org_role,
            title=body.title,
            capabilities=body.capabilities,
        )
    except ValueError as exc:
        detail = str(exc)
        if "cycle" in detail:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail,
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return AgentSummary(
        agent_id=node.agent_id,
        name=node.name,
        org_role=node.org_role,
        title=node.title,
    )


@router.put(
    "/{agent_id}/org",
    response_model=AgentSummary,
    tags=["agent-org"],
    status_code=status.HTTP_200_OK,
)
async def upsert_agent_org(
    agent_id: str,
    body: UpsertOrgRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AgentSummary:
    """
    Register or update an agent in the org hierarchy (#1405).

    Creates the record if it does not exist.
    """
    svc = AgentOrgService(session)
    node = await svc.upsert_node(
        agent_id=agent_id,
        name=body.name,
        org_role=body.org_role,
        reports_to=body.reports_to,
        title=body.title,
        capabilities=body.capabilities,
    )
    return AgentSummary(
        agent_id=node.agent_id,
        name=node.name,
        org_role=node.org_role,
        title=node.title,
    )


@router.get(
    "/{agent_id}/org/role-defaults",
    response_model=Dict[str, Any],
    tags=["agent-org"],
)
async def get_role_defaults(
    agent_id: str,
    role: str,
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Return default permission set for the given org role (#1405)."""
    svc = AgentOrgService(session)
    return svc.get_role_defaults(role)
