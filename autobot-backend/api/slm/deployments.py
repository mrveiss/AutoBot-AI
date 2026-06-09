# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM Deployments API

Exposes HTTP endpoints so autobot-backend callers can trigger and query Docker
container deployments through the SLM Ansible playbook runner without talking
directly to the SLM backend.

Endpoints
---------
POST   /slm/deployments/docker          Trigger a Docker deployment
POST   /slm/deployments                 Create a generic multi-role deployment
GET    /slm/deployments                 List active deployments
GET    /slm/deployments/{id}            Get a deployment by ID
POST   /slm/deployments/{id}/execute    Execute a queued deployment
POST   /slm/deployments/{id}/cancel     Cancel a deployment
POST   /slm/deployments/{id}/rollback   Rollback a deployment

Related to Issue #3407.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth_middleware import get_current_user
from autobot_shared.logging_manager import get_logger
from models.infrastructure import (
    DeploymentActionResponse,
    DeploymentCreateRequest,
    DeploymentStrategy,
    DockerDeploymentRequest,
    DockerDeploymentStatus,
)
from services.slm.deployment_bridge import (
    DeploymentContext,
    DeploymentCoordinator,
    DeploymentStatus,
    SLMDeploymentBridge,
    get_orchestrator,
)
from services.slm_client import get_slm_client

logger = get_logger(__name__)

router = APIRouter(
    prefix="/slm/deployments",
    tags=["slm-deployments"],
    dependencies=[Depends(get_current_user)],
)

_VALID_STRATEGIES = {s.value for s in DeploymentStrategy}


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def _require_orchestrator() -> DeploymentCoordinator:
    """Return the global orchestrator or raise 503 if not initialised."""
    orch = get_orchestrator()
    if orch is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Deployment orchestrator not initialised",
        )
    return orch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _context_to_dict(ctx: DeploymentContext) -> dict:
    """Serialise a DeploymentContext to a response dict."""
    return {
        "deployment_id": ctx.deployment_id,
        "role_name": ctx.role_name,
        "target_nodes": ctx.target_nodes,
        "strategy": (ctx.strategy.value if hasattr(ctx.strategy, "value") else ctx.strategy),
        "playbook_path": ctx.playbook_path,
        "status": ctx.status.value if hasattr(ctx.status, "value") else ctx.status,
        "steps": [
            {
                "step_type": (s.step_type.value if hasattr(s.step_type, "value") else s.step_type),
                "node_id": s.node_id,
                "node_name": s.node_name,
                "description": s.description,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "success": s.success,
                "error": s.error,
            }
            for s in ctx.steps
        ],
        "started_at": ctx.started_at.isoformat() if ctx.started_at else None,
        "completed_at": ctx.completed_at.isoformat() if ctx.completed_at else None,
        "error": ctx.error,
    }


# ---------------------------------------------------------------------------
# Docker-specific route (issue requirement)
# ---------------------------------------------------------------------------


@router.post(
    "/docker",
    response_model=DockerDeploymentStatus,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a Docker container deployment via SLM",
)
async def deploy_docker(request: DockerDeploymentRequest) -> DockerDeploymentStatus:
    """
    Trigger deployment of one or more Docker containers on the target node.

    The SLM runs the configured Ansible playbook (default:
    deploy-hybrid-docker.yml) and returns a deployment record.
    """
    client = get_slm_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SLM client not initialised",
        )
    slm_orch = SLMDeploymentBridge(client)
    result = await slm_orch.deploy_docker(request)
    logger.info(
        "Docker deployment triggered: %s on node %s",
        result.deployment_id,
        result.node_id,
    )
    return result


# ---------------------------------------------------------------------------
# Generic multi-role deployment routes
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a generic multi-role deployment",
)
async def create_deployment(
    body: DeploymentCreateRequest,
    orch: DeploymentCoordinator = Depends(_require_orchestrator),
) -> Any:
    """Create and queue a new multi-role, multi-node deployment."""
    if body.strategy.value not in _VALID_STRATEGIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid strategy: {body.strategy}",
        )
    ctx = await orch.create_deployment(
        role_name=body.role_name,
        target_nodes=body.target_nodes,
        strategy=body.strategy,
        playbook_path=body.playbook_path,
    )
    return _context_to_dict(ctx)


@router.get("", summary="List active deployments")
async def list_deployments(
    status_filter: str | None = Query(None),
    orch: DeploymentCoordinator = Depends(_require_orchestrator),
) -> Any:
    """Return active deployments, optionally filtered by status string."""
    deployments = orch.active_deployments
    if status_filter:
        deployments = [
            d for d in deployments if (d.status.value if hasattr(d.status, "value") else d.status) == status_filter
        ]
    return {
        "deployments": [_context_to_dict(d) for d in deployments],
        "total": len(deployments),
    }


@router.get("/{deployment_id}", summary="Get a deployment by ID")
async def get_deployment(
    deployment_id: str,
    orch: DeploymentCoordinator = Depends(_require_orchestrator),
) -> Any:
    """Return a single deployment context by its ID."""
    ctx = orch.get_deployment(deployment_id)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )
    return _context_to_dict(ctx)


@router.post("/{deployment_id}/execute", summary="Execute a queued deployment")
async def execute_deployment(
    deployment_id: str,
    orch: DeploymentCoordinator = Depends(_require_orchestrator),
) -> Any:
    """Start execution of a deployment that is in QUEUED state."""
    ctx = orch.get_deployment(deployment_id)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )
    if ctx.status != DeploymentStatus.QUEUED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Deployment is not queued (current status: {ctx.status})",
        )
    ok = await orch.execute_deployment(deployment_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not execute deployment {deployment_id!r}",
        )
    logger.info("Deployment execution started: %s", deployment_id)
    return DeploymentActionResponse(deployment_id=deployment_id, action="execute", success=True)


@router.post("/{deployment_id}/cancel", summary="Cancel a deployment")
async def cancel_deployment(
    deployment_id: str,
    orch: DeploymentCoordinator = Depends(_require_orchestrator),
) -> Any:
    """Cancel a queued or running deployment."""
    ctx = orch.get_deployment(deployment_id)
    cancelled = await orch.cancel_deployment(deployment_id)
    if not cancelled:
        if ctx is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deployment not found",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deployment cannot be cancelled in its current state",
        )
    logger.info("Deployment cancelled: %s", deployment_id)
    return DeploymentActionResponse(deployment_id=deployment_id, action="cancel", success=True)


@router.post("/{deployment_id}/rollback", summary="Rollback a deployment")
async def rollback_deployment(
    deployment_id: str,
    orch: DeploymentCoordinator = Depends(_require_orchestrator),
) -> Any:
    """Trigger rollback for a deployment."""
    ctx = orch.get_deployment(deployment_id)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )
    success = await orch.trigger_rollback(deployment_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No deployed nodes to roll back",
        )
    logger.info("Rollback triggered for deployment %s", deployment_id)
    return DeploymentActionResponse(deployment_id=deployment_id, action="rollback", success=True)
