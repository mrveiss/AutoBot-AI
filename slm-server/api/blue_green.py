# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Blue-Green Deployment API Routes

Provides endpoints for zero-downtime deployments with role borrowing.
"""

import logging
from typing import Optional

from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.schemas import (
    BlueGreenCreate,
    BlueGreenResponse,
    BlueGreenListResponse,
    BlueGreenActionResponse,
    EligibleNodesResponse,
    RolePurgeRequest,
    RolePurgeResponse,
)
from services.auth import get_current_user, require_admin
from services.blue_green import blue_green_service
from services.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/blue-green", tags=["blue-green"])

# Deployment ID validation pattern (8 hex characters from UUID)
DEPLOYMENT_ID_PATTERN = r"^[a-f0-9]{8}$"
DeploymentIdPath = Annotated[
    str,
    Path(
        ...,
        pattern=DEPLOYMENT_ID_PATTERN,
        description="Blue-green deployment ID (8 hex characters)",
        examples=["a1b2c3d4"],
    ),
]


@router.get("", response_model=BlueGreenListResponse)
async def list_deployments(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> BlueGreenListResponse:
    """List blue-green deployments with optional status filter."""
    deployments, total = await blue_green_service.list_deployments(
        db, status_filter, page, per_page
    )

    return BlueGreenListResponse(
        deployments=deployments,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=BlueGreenResponse, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    data: BlueGreenCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(require_admin)],
) -> BlueGreenResponse:
    """Create a new blue-green deployment (admin only).

    Blue-green deployments allow zero-downtime role migrations:
    - Blue node: Current production node running the roles
    - Green node: Standby node that will temporarily borrow the roles
    - Auto-rollback: Automatically revert if health checks fail
    """
    try:
        deployment = await blue_green_service.create_deployment(
            db, data, triggered_by=current_user.get("sub", "unknown")
        )
        logger.info(
            "Blue-green deployment created: %s by %s",
            deployment.bg_deployment_id,
            current_user.get("sub"),
        )
        return deployment
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/eligible-nodes", response_model=EligibleNodesResponse)
async def find_eligible_nodes(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    roles: str = Query(..., description="Comma-separated list of roles"),
) -> EligibleNodesResponse:
    """Find nodes eligible to borrow the specified roles.

    Returns nodes that:
    - Are currently online
    - Have sufficient CPU/memory headroom (>30%)
    - Are not already running the specified roles
    """
    role_list = [r.strip() for r in roles.split(",")]
    nodes = await blue_green_service.find_eligible_nodes(db, role_list)

    return EligibleNodesResponse(nodes=nodes, total=len(nodes))


@router.get("/{bg_deployment_id}", response_model=BlueGreenResponse)
async def get_deployment(
    bg_deployment_id: DeploymentIdPath,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> BlueGreenResponse:
    """Get a blue-green deployment by ID."""
    deployment = await blue_green_service.get_deployment(db, bg_deployment_id)

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blue-green deployment not found",
        )

    return deployment


@router.post("/{bg_deployment_id}/switch", response_model=BlueGreenActionResponse)
async def switch_traffic(
    bg_deployment_id: DeploymentIdPath,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> BlueGreenActionResponse:
    """Manually trigger traffic switch from blue to green (admin only).

    Only available when deployment is in 'verifying' status.
    """
    success, message = await blue_green_service.switch_traffic(db, bg_deployment_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    logger.info("Traffic switch triggered for deployment: %s", bg_deployment_id)
    return BlueGreenActionResponse(
        action="switch",
        bg_deployment_id=bg_deployment_id,
        success=True,
        message=message,
    )


@router.post("/{bg_deployment_id}/rollback", response_model=BlueGreenActionResponse)
async def rollback_deployment(
    bg_deployment_id: DeploymentIdPath,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> BlueGreenActionResponse:
    """Rollback a blue-green deployment (admin only).

    Reverts traffic to the blue node and purges borrowed roles from green.
    """
    success, message = await blue_green_service.rollback(db, bg_deployment_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    logger.info("Rollback initiated for deployment: %s", bg_deployment_id)
    return BlueGreenActionResponse(
        action="rollback",
        bg_deployment_id=bg_deployment_id,
        success=True,
        message=message,
    )


@router.post("/{bg_deployment_id}/cancel", response_model=BlueGreenActionResponse)
async def cancel_deployment(
    bg_deployment_id: DeploymentIdPath,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> BlueGreenActionResponse:
    """Cancel a pending blue-green deployment (admin only)."""
    success, message = await blue_green_service.cancel(db, bg_deployment_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    logger.info("Deployment cancelled: %s", bg_deployment_id)
    return BlueGreenActionResponse(
        action="cancel",
        bg_deployment_id=bg_deployment_id,
        success=True,
        message=message,
    )


@router.post("/{bg_deployment_id}/retry", response_model=BlueGreenActionResponse)
async def retry_deployment(
    bg_deployment_id: DeploymentIdPath,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(require_admin)],
) -> BlueGreenActionResponse:
    """Retry a failed blue-green deployment (admin only).

    Resets the deployment status and restarts the deployment workflow.
    Only available for deployments in 'failed' status.
    """
    success, message = await blue_green_service.retry(
        db, bg_deployment_id, triggered_by=current_user.get("sub", "unknown")
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    logger.info("Blue-green deployment retry initiated: %s", bg_deployment_id)
    return BlueGreenActionResponse(
        action="retry",
        bg_deployment_id=bg_deployment_id,
        success=True,
        message=message,
    )


@router.post("/{bg_deployment_id}/stop-monitoring", response_model=BlueGreenActionResponse)
async def stop_monitoring(
    bg_deployment_id: DeploymentIdPath,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> BlueGreenActionResponse:
    """Stop post-deployment health monitoring and complete the deployment (admin only).

    Issue #726 Phase 3: Allows manual completion of deployment during monitoring phase.
    Use this to skip remaining monitoring time when confident the deployment is healthy.
    """
    success, message = await blue_green_service.complete_monitoring(db, bg_deployment_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    logger.info("Monitoring stopped for deployment: %s", bg_deployment_id)
    return BlueGreenActionResponse(
        action="stop_monitoring",
        bg_deployment_id=bg_deployment_id,
        success=True,
        message=message,
    )


@router.post("/purge", response_model=RolePurgeResponse)
async def purge_roles(
    data: RolePurgeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> RolePurgeResponse:
    """Purge roles from a node (admin only).

    This performs a clean slate removal of specified roles:
    - Stops all associated services
    - Removes service files
    - Cleans up role-specific data directories

    Use with caution - this is destructive!
    """
    try:
        success, message, stopped_services = await blue_green_service.purge_roles(
            db, data.node_id, data.roles, data.force
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message,
            )

        logger.info("Roles purged from node %s: %s", data.node_id, data.roles)
        return RolePurgeResponse(
            success=True,
            message=message,
            purged_roles=data.roles,
            node_id=data.node_id,
            services_stopped=stopped_services,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
