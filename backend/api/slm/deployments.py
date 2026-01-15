# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Deployments API

REST endpoints for deployment management:
- Create deployments
- Execute deployments
- Monitor deployment progress
- Cancel/rollback deployments
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from backend.models.infrastructure import DeploymentStrategy as DeploymentStrategyType
from backend.services.slm.deployment_orchestrator import (
    DeploymentContext,
    DeploymentOrchestrator,
    DeploymentStatus,
    DeploymentStep,
    DeploymentStepType,
    get_orchestrator,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slm/deployments", tags=["SLM Deployments"])


# ==================== Pydantic Models ====================


class DeploymentCreate(BaseModel):
    """Request model for creating a deployment."""

    role_name: str = Field(..., min_length=1, max_length=100)
    target_nodes: List[str] = Field(..., min_items=1)
    strategy: str = Field(
        default="sequential",
        description="Deployment strategy: sequential, blue_green, maintenance_window",
    )
    playbook_path: Optional[str] = Field(
        default=None,
        description="Path to Ansible playbook to execute",
    )
    params: Dict = Field(
        default_factory=dict,
        description="Additional deployment parameters",
    )


class DeploymentStepResponse(BaseModel):
    """Response model for a deployment step."""

    step_type: str
    node_id: str
    node_name: str
    description: str
    started_at: Optional[str]
    completed_at: Optional[str]
    success: bool
    error: Optional[str]


class DeploymentResponse(BaseModel):
    """Response model for deployment data."""

    deployment_id: str
    strategy: str
    role_name: str
    target_nodes: List[str]
    playbook_path: Optional[str]
    status: str
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]
    rollback_triggered: bool
    steps: List[DeploymentStepResponse]

    class Config:
        from_attributes = True


class DeploymentListResponse(BaseModel):
    """Response model for deployment list."""

    deployments: List[DeploymentResponse]
    total: int


class DeploymentActionResponse(BaseModel):
    """Response for deployment actions."""

    deployment_id: str
    action: str
    success: bool
    message: str


# ==================== Helper Functions ====================


def _step_to_response(step: DeploymentStep) -> DeploymentStepResponse:
    """Convert a DeploymentStep to response model."""
    return DeploymentStepResponse(
        step_type=step.step_type.value,
        node_id=step.node_id,
        node_name=step.node_name,
        description=step.description,
        started_at=step.started_at.isoformat() if step.started_at else None,
        completed_at=step.completed_at.isoformat() if step.completed_at else None,
        success=step.success,
        error=step.error,
    )


def _context_to_response(ctx: DeploymentContext) -> DeploymentResponse:
    """Convert a DeploymentContext to response model."""
    return DeploymentResponse(
        deployment_id=ctx.deployment_id,
        strategy=ctx.strategy.value,
        role_name=ctx.role_name,
        target_nodes=ctx.target_nodes,
        playbook_path=ctx.playbook_path,
        status=ctx.status.value,
        started_at=ctx.started_at.isoformat() if ctx.started_at else None,
        completed_at=ctx.completed_at.isoformat() if ctx.completed_at else None,
        error=ctx.error,
        rollback_triggered=ctx.rollback_triggered,
        steps=[_step_to_response(s) for s in ctx.steps],
    )


def _parse_strategy(strategy_str: str) -> DeploymentStrategyType:
    """Parse strategy string to enum."""
    strategy_map = {
        "sequential": DeploymentStrategyType.SEQUENTIAL,
        "blue_green": DeploymentStrategyType.BLUE_GREEN,
        "maintenance_window": DeploymentStrategyType.MAINTENANCE_WINDOW,
        "replicated_swap": DeploymentStrategyType.REPLICATED_SWAP,
    }

    if strategy_str.lower() not in strategy_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid strategy: {strategy_str}. "
            f"Valid options: {list(strategy_map.keys())}",
        )

    return strategy_map[strategy_str.lower()]


# ==================== Endpoints ====================


@router.get("", response_model=DeploymentListResponse)
async def list_deployments(
    status_filter: Optional[str] = None,
):
    """
    List all active deployments.

    Args:
        status_filter: Optional status to filter by
    """
    orchestrator = get_orchestrator()
    deployments = orchestrator.active_deployments

    # Filter by status if provided
    if status_filter:
        deployments = [d for d in deployments if d.status.value == status_filter]

    return DeploymentListResponse(
        deployments=[_context_to_response(d) for d in deployments],
        total=len(deployments),
    )


@router.post("", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    request: DeploymentCreate,
):
    """
    Create a new deployment.

    The deployment will be queued and can be executed later via
    POST /deployments/{id}/execute.
    """
    orchestrator = get_orchestrator()

    # Parse strategy first (may raise HTTPException)
    strategy = _parse_strategy(request.strategy)

    try:
        context = await orchestrator.create_deployment(
            role_name=request.role_name,
            target_nodes=request.target_nodes,
            strategy=strategy,
            playbook_path=request.playbook_path,
            params=request.params,
        )

        logger.info(
            "Created deployment %s: role=%s, nodes=%d",
            context.deployment_id,
            request.role_name,
            len(request.target_nodes),
        )

        return _context_to_response(context)

    except Exception as e:
        logger.exception("Failed to create deployment: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(deployment_id: str):
    """Get deployment details by ID."""
    orchestrator = get_orchestrator()
    context = orchestrator.get_deployment(deployment_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deployment {deployment_id} not found",
        )

    return _context_to_response(context)


@router.post("/{deployment_id}/execute", response_model=DeploymentActionResponse)
async def execute_deployment(
    deployment_id: str,
    background_tasks: BackgroundTasks,
):
    """
    Execute a queued deployment.

    The deployment will run in the background. Monitor progress
    via GET /deployments/{id} or WebSocket events.
    """
    orchestrator = get_orchestrator()
    context = orchestrator.get_deployment(deployment_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deployment {deployment_id} not found",
        )

    if context.status != DeploymentStatus.QUEUED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot execute deployment in status: {context.status.value}",
        )

    # Execute in background
    background_tasks.add_task(orchestrator.execute_deployment, deployment_id)

    logger.info("Started execution of deployment %s", deployment_id)

    return DeploymentActionResponse(
        deployment_id=deployment_id,
        action="execute",
        success=True,
        message="Deployment execution started",
    )


@router.post("/{deployment_id}/cancel", response_model=DeploymentActionResponse)
async def cancel_deployment(deployment_id: str):
    """
    Cancel a queued or paused deployment.

    Running deployments cannot be cancelled directly.
    """
    orchestrator = get_orchestrator()

    success = await orchestrator.cancel_deployment(deployment_id)

    if not success:
        context = orchestrator.get_deployment(deployment_id)
        if not context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Deployment {deployment_id} not found",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel deployment in status: {context.status.value}",
        )

    logger.info("Cancelled deployment %s", deployment_id)

    return DeploymentActionResponse(
        deployment_id=deployment_id,
        action="cancel",
        success=True,
        message="Deployment cancelled",
    )


@router.post("/{deployment_id}/rollback", response_model=DeploymentActionResponse)
async def rollback_deployment(deployment_id: str):
    """
    Trigger manual rollback for a deployment.

    Rolls back all successfully deployed nodes to their
    previous state.
    """
    orchestrator = get_orchestrator()
    context = orchestrator.get_deployment(deployment_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deployment {deployment_id} not found",
        )

    success = await orchestrator.trigger_rollback(deployment_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No nodes to rollback or rollback failed",
        )

    logger.info("Triggered rollback for deployment %s", deployment_id)

    return DeploymentActionResponse(
        deployment_id=deployment_id,
        action="rollback",
        success=True,
        message="Rollback initiated",
    )
