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
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from services.agent_org_service import AgentOrgService
from services.delegation_service import DelegationService
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
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request failed"
        )
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


# -- Delegation schemas (#1753) -------------------------------------------


class DelegateRequest(BaseModel):
    """Request body for POST /{manager_id}/delegate (#1753)."""

    assignee_id: str = Field(..., description="Direct report to assign to")
    task_description: str = Field(..., description="What the assignee should do")
    context: Optional[Dict[str, Any]] = Field(
        default=None, description="Extra context for the task"
    )


class DelegationResponse(BaseModel):
    """Response for a task delegation (#1753)."""

    id: str
    delegator_id: str
    assignee_id: str
    task_description: str
    status: str
    escalated_to: Optional[str] = None
    created_at: Optional[str] = None


class DelegationStatusUpdate(BaseModel):
    """Request body for PATCH /delegations/{id}/status (#1753)."""

    status: str = Field(..., description="New status value")
    result: Optional[Dict[str, Any]] = None


def _delegation_to_response(d) -> DelegationResponse:
    """Convert TaskDelegation ORM row to response (#1753)."""
    return DelegationResponse(
        id=str(d.id),
        delegator_id=d.delegator_id,
        assignee_id=d.assignee_id,
        task_description=d.task_description,
        status=d.status,
        escalated_to=d.escalated_to,
        created_at=d.created_at.isoformat() if d.created_at else None,
    )


# -- Delegation endpoints (#1753) ----------------------------------------


@router.post(
    "/{manager_id}/delegate",
    response_model=DelegationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["agent-delegation"],
)
async def delegate_task(
    manager_id: str,
    body: DelegateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> DelegationResponse:
    """
    Assign a task from a manager to one of its direct reports (#1753).

    Validates reporting relationship and delegation permission.
    """
    svc = DelegationService(session)
    try:
        delegation = await svc.delegate_task(
            delegator_id=manager_id,
            assignee_id=body.assignee_id,
            task_description=body.task_description,
            context=body.context,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Request failed"
        )
    return _delegation_to_response(delegation)


@router.post(
    "/delegations/{delegation_id}/escalate",
    response_model=DelegationResponse,
    tags=["agent-delegation"],
)
async def escalate_delegation(
    delegation_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> DelegationResponse:
    """
    Escalate a stuck/failed delegation up the chain of command (#1753).
    """
    svc = DelegationService(session)
    try:
        delegation = await svc.escalate_task(delegation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Request failed"
        )
    return _delegation_to_response(delegation)


@router.patch(
    "/delegations/{delegation_id}/status",
    response_model=DelegationResponse,
    tags=["agent-delegation"],
)
async def update_delegation_status(
    delegation_id: str,
    body: DelegationStatusUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> DelegationResponse:
    """Update the status of a delegated task (#1753)."""
    svc = DelegationService(session)
    try:
        delegation = await svc.update_status(delegation_id, body.status, body.result)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request failed"
        )
    return _delegation_to_response(delegation)


@router.get(
    "/{agent_id}/activity",
    response_model=Dict[str, Any],
    tags=["agent-delegation"],
)
async def get_delegation_activity(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Aggregate delegation activity for a manager (#1753)."""
    svc = DelegationService(session)
    return await svc.get_activity_summary(agent_id)


@router.get(
    "/{agent_id}/delegations",
    response_model=List[DelegationResponse],
    tags=["agent-delegation"],
)
async def list_agent_delegations(
    agent_id: str,
    role: str = Query(
        default="delegator",
        description="Filter by 'delegator' or 'assignee'",
    ),
    delegation_status: Optional[str] = Query(
        default=None, alias="status", description="Filter by status"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> List[DelegationResponse]:
    """List delegations for an agent as delegator or assignee (#1753)."""
    svc = DelegationService(session)
    delegations = await svc.list_delegations(
        agent_id=agent_id,
        role=role,
        status_filter=delegation_status,
        limit=limit,
    )
    return [_delegation_to_response(d) for d in delegations]
