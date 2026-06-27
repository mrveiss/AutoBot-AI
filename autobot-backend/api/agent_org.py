# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Org API (#1405)

Endpoints for agent organizational hierarchy: org tree, chain of command,
direct reports, and org metadata updates with cycle detection.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_agent import (
    AgentDelegateRequest,
    AgentStatusItem,
    AgentStatusListResponse,
    AgentSummary,
    ChainOfCommandResponse,
    DelegationResponse,
    DelegationStatusUpdate,
    OrgNodeResponse,
    UpdateOrgRequest,
    UpsertOrgRequest,
)
from api.user_management.dependencies import get_db_session, get_optional_db_session
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.agent_org_service import AgentOrgService
from services.delegation_service import DelegationService

logger = get_logger(__name__)
router = APIRouter()


# -- Fallback: in-memory agents when PG is unavailable (#10511) ------------

# Map from orchestration agent_type to the activity-monitor "type" vocabulary.
_ORCH_TYPE_MAP: Dict[str, str] = {
    "research": "analyzer",
    "librarian": "analyzer",
    "system_commands": "executor",
    "orchestrator": "orchestrator",
}


def _fallback_agents_from_registry() -> List[Dict[str, Any]]:
    """Build agent list from the in-memory AgentRegistry when PG is unavailable (#10511).

    Returns the same shape as ``AgentOrgService.get_agent_statuses()`` so the
    caller can treat both sources uniformly.
    """
    try:
        from orchestration.agent_registry import AgentRegistry

        registry = AgentRegistry(initialize_defaults=True)
        agents = []
        for profile in registry.get_all().values():
            agents.append(
                {
                    "id": profile.agent_id,
                    "name": profile.agent_id.replace("_", " ").title(),
                    "type": _ORCH_TYPE_MAP.get(profile.agent_type, "worker"),
                    "status": profile.availability_status,
                    "currentTask": None,
                    "tasksCompleted": 0,
                    "uptime": 0,
                    "successRate": int(profile.success_rate * 100),
                    "recentTasks": [],
                    "activityTimeline": [],
                }
            )
        return agents
    except Exception as exc:
        logger.debug("Fallback agent registry unavailable: %s", exc)
        return []


# -- Endpoints -------------------------------------------------------------


@router.get(
    "/org",
    response_model=List[OrgNodeResponse],
    tags=["agent-org"],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_org_tree",
    error_code_prefix="AGENT_ORG",
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
    "/status",
    response_model=AgentStatusListResponse,
    tags=["agent-org"],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agents_status",
    error_code_prefix="AGENT_ORG",
)
async def get_agents_status(
    session: Optional[AsyncSession] = Depends(get_optional_db_session),
) -> AgentStatusListResponse:
    """Return all registered agents with runtime status (#10502, #10511).

    PG-optional: when PostgreSQL is disabled (single_user mode) the endpoint
    falls back to the in-memory ``AgentRegistry`` populated from
    ``DEFAULT_AGENT_CONFIGS`` so the Home dashboard "Agent Activity Monitor"
    returns 200 instead of 503.
    """
    if session is not None:
        svc = AgentOrgService(session)
        agents = await svc.get_agent_statuses()
    else:
        logger.debug("PG unavailable — returning in-memory agents for /agents/status (#10511)")
        agents = _fallback_agents_from_registry()

    items = [AgentStatusItem(**a) for a in agents]
    return AgentStatusListResponse(agents=items, total=len(items))


@router.get(
    "/{agent_id}/chain",
    response_model=ChainOfCommandResponse,
    tags=["agent-org"],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_chain_of_command",
    error_code_prefix="AGENT_ORG",
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request failed")
    return ChainOfCommandResponse(chain=[AgentSummary(**item) for item in chain])


@router.get(
    "/{agent_id}/reports",
    response_model=List[AgentSummary],
    tags=["agent-org"],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_direct_reports",
    error_code_prefix="AGENT_ORG",
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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_agent_org",
    error_code_prefix="AGENT_ORG",
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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="upsert_agent_org",
    error_code_prefix="AGENT_ORG",
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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_role_defaults",
    error_code_prefix="AGENT_ORG",
)
async def get_role_defaults(
    agent_id: str,
    role: str,
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Return default permission set for the given org role (#1405)."""
    svc = AgentOrgService(session)
    return svc.get_role_defaults(role)


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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delegate_task",
    error_code_prefix="AGENT_ORG",
)
async def delegate_task(
    manager_id: str,
    body: AgentDelegateRequest,
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request failed")
    return _delegation_to_response(delegation)


@router.post(
    "/delegations/{delegation_id}/escalate",
    response_model=DelegationResponse,
    tags=["agent-delegation"],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="escalate_delegation",
    error_code_prefix="AGENT_ORG",
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request failed")
    return _delegation_to_response(delegation)


@router.patch(
    "/delegations/{delegation_id}/status",
    response_model=DelegationResponse,
    tags=["agent-delegation"],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_delegation_status",
    error_code_prefix="AGENT_ORG",
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request failed")
    return _delegation_to_response(delegation)


@router.get(
    "/{agent_id}/activity",
    response_model=Dict[str, Any],
    tags=["agent-delegation"],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_delegation_activity",
    error_code_prefix="AGENT_ORG",
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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_agent_delegations",
    error_code_prefix="AGENT_ORG",
)
async def list_agent_delegations(
    agent_id: str,
    role: str = Query(
        default="delegator",
        description="Filter by 'delegator' or 'assignee'",
    ),
    delegation_status: str | None = Query(default=None, alias="status", description="Filter by status"),
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
