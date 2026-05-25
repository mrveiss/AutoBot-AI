# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Budget Policy CRUD API (GH#6470)

Endpoints for creating, updating, listing, and managing budget policies.
Supports scoped budget thresholds with hard-stop auto-pause for runaway agent spend.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_db_session
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from models.heartbeat import AgentRuntimeState
from services.budget_policy import (
    BudgetPolicy,
    create_policy,
    delete_policy,
    get_policy,
    list_all_policies,
    list_policies_for_scope,
    patch_policy,
    resume_agent,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/budget-policies")


class BudgetPolicyRequest(BaseModel):
    """Request schema for creating/updating a budget policy."""

    scope: str = Field(..., description="Scope: agent, project, task, or tenant")
    scope_id: str = Field(..., description="Resource ID for the scope")
    period: str = Field(..., description="Period: hour, day, or month")
    threshold_usd: float = Field(..., gt=0, description="Hard-stop threshold in USD")
    warning_pct: float = Field(default=0.8, ge=0, le=1, description="Warning threshold as % of hard-stop (0-1)")
    action: str = Field(
        default="alert_then_pause",
        description="Action on breach: alert, pause, or alert_then_pause",
    )
    enabled: bool = Field(default=True, description="Enable/disable the policy")
    name: str = Field(default="", description="Human-readable name")
    description: str = Field(default="", description="Policy description")


class BudgetPolicyResponse(BaseModel):
    """Response schema for a budget policy."""

    id: str
    scope: str
    scope_id: str
    period: str
    threshold_usd: float
    warning_pct: float
    action: str
    enabled: bool
    name: str
    description: str
    created_at: str
    updated_at: str


class BudgetPoliciesListResponse(BaseModel):
    """Response schema for listing policies."""

    policies: List[BudgetPolicyResponse]
    count: int


class ResumeAgentResponse(BaseModel):
    """Response for agent resume operation."""

    success: bool
    message: str


class PauseStatusResponse(BaseModel):
    """Response for agent pause status query."""

    agent_id: str
    is_paused: bool
    paused_reason: Optional[str] = None
    paused_at: Optional[str] = None


def _policy_to_response(policy: BudgetPolicy) -> BudgetPolicyResponse:
    """Convert a BudgetPolicy model to response."""
    return BudgetPolicyResponse(
        id=policy.id,
        scope=policy.scope,
        scope_id=policy.scope_id,
        period=policy.period,
        threshold_usd=policy.threshold_usd,
        warning_pct=policy.warning_pct,
        action=policy.action,
        enabled=policy.enabled,
        name=policy.name,
        description=policy.description,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@router.post("", response_model=BudgetPolicyResponse, status_code=status.HTTP_201_CREATED)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_budget_policy",
    error_code_prefix="BUDGET",
)
async def create_budget_policy(
    body: BudgetPolicyRequest,
    _user=Depends(get_current_user),
) -> BudgetPolicyResponse:
    """Create a new budget policy."""
    policy = BudgetPolicy(
        scope=body.scope,
        scope_id=body.scope_id,
        period=body.period,
        threshold_usd=body.threshold_usd,
        warning_pct=body.warning_pct,
        action=body.action,
        enabled=body.enabled,
        name=body.name,
        description=body.description,
    )
    created = await create_policy(policy)
    return _policy_to_response(created)


@router.get("", response_model=BudgetPoliciesListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_budget_policies",
    error_code_prefix="BUDGET",
)
async def list_budget_policies(
    scope: Optional[str] = Query(None, description="Filter by scope (optional)"),
    scope_id: Optional[str] = Query(None, description="Filter by scope_id (optional)"),
    _user=Depends(get_current_user),
) -> BudgetPoliciesListResponse:
    """List budget policies, optionally filtered by scope."""
    if scope and scope_id:
        policies = await list_policies_for_scope(scope, scope_id)
    else:
        policies = await list_all_policies()

    responses = [_policy_to_response(p) for p in policies]
    return BudgetPoliciesListResponse(policies=responses, count=len(responses))


@router.get("/{policy_id}", response_model=BudgetPolicyResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_budget_policy",
    error_code_prefix="BUDGET",
)
async def get_budget_policy(
    policy_id: str,
    _user=Depends(get_current_user),
) -> BudgetPolicyResponse:
    """Get a single budget policy by ID."""
    policy = await get_policy(policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return _policy_to_response(policy)


@router.patch("/{policy_id}", response_model=BudgetPolicyResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_budget_policy",
    error_code_prefix="BUDGET",
)
async def update_budget_policy(
    policy_id: str,
    body: BudgetPolicyRequest,
    _user=Depends(get_current_user),
) -> BudgetPolicyResponse:
    """Update a budget policy."""
    existing = await get_policy(policy_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")

    updates = {
        "scope": body.scope,
        "scope_id": body.scope_id,
        "period": body.period,
        "threshold_usd": body.threshold_usd,
        "warning_pct": body.warning_pct,
        "action": body.action,
        "enabled": body.enabled,
        "name": body.name,
        "description": body.description,
    }
    updated = await patch_policy(policy_id, updates)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return _policy_to_response(updated)


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_budget_policy",
    error_code_prefix="BUDGET",
)
async def delete_budget_policy(
    policy_id: str,
    _user=Depends(get_current_user),
) -> None:
    """Delete a budget policy."""
    success = await delete_policy(policy_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")


@router.post(
    "/{agent_id}/resume",
    response_model=ResumeAgentResponse,
    status_code=status.HTTP_200_OK,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resume_agent",
    error_code_prefix="BUDGET",
)
async def resume_paused_agent(
    agent_id: str,
    _admin: bool = Depends(check_admin_permission),
) -> ResumeAgentResponse:
    """Resume a budget-paused agent (admin only)."""
    success = await resume_agent(agent_id, approved_by="admin")
    if not success:
        return ResumeAgentResponse(
            success=False,
            message=f"Agent {agent_id} is not paused or not found",
        )
    return ResumeAgentResponse(
        success=True,
        message=f"Agent {agent_id} resumed successfully",
    )


@router.get("/{agent_id}/status", response_model=PauseStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pause_status",
    error_code_prefix="BUDGET",
)
async def get_agent_pause_status(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    _user=Depends(get_current_user),
) -> PauseStatusResponse:
    """Get the pause status of an agent."""
    try:
        result = await session.execute(
            select(AgentRuntimeState).where(AgentRuntimeState.agent_id == agent_id)
        )
        state = result.scalar_one_or_none()

        if state is None or state.status != "paused":
            return PauseStatusResponse(
                agent_id=agent_id,
                is_paused=False,
                paused_reason=None,
                paused_at=None,
            )

        return PauseStatusResponse(
            agent_id=agent_id,
            is_paused=True,
            paused_reason=state.paused_reason,
            paused_at=state.paused_at.isoformat() if state.paused_at else None,
        )
    except Exception as e:
        logger.error("Failed to get pause status for agent=%s: %s", agent_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check pause status",
        )
