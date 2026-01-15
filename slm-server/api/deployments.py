# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Deployments API Routes
"""

import logging
from typing import Optional

from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.schemas import (
    DeploymentCreate,
    DeploymentListResponse,
    DeploymentResponse,
    RoleInfo,
    RoleListResponse,
)
from services.auth import get_current_user
from services.database import get_db
from services.deployment import deployment_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/deployments", tags=["deployments"])

AVAILABLE_ROLES = [
    RoleInfo(
        name="slm-agent",
        description="SLM monitoring agent for node health reporting",
        category="core",
        dependencies=[],
        variables={"heartbeat_interval": 30},
    ),
    RoleInfo(
        name="redis",
        description="Redis Stack server for data persistence",
        category="data",
        dependencies=["slm-agent"],
        variables={"port": 6379, "cluster_enabled": False},
    ),
    RoleInfo(
        name="backend",
        description="AutoBot backend API server",
        category="application",
        dependencies=["slm-agent", "redis"],
        variables={"port": 8001, "workers": 4},
    ),
    RoleInfo(
        name="frontend",
        description="AutoBot Vue.js frontend server",
        category="application",
        dependencies=["slm-agent"],
        variables={"port": 5173},
    ),
    RoleInfo(
        name="npu-worker",
        description="Intel NPU acceleration worker",
        category="ai",
        dependencies=["slm-agent"],
        variables={"device_id": 0},
    ),
    RoleInfo(
        name="browser-automation",
        description="Playwright browser automation service",
        category="automation",
        dependencies=["slm-agent"],
        variables={"headless": True},
    ),
    RoleInfo(
        name="monitoring",
        description="Prometheus and Grafana monitoring stack",
        category="observability",
        dependencies=["slm-agent"],
        variables={"prometheus_port": 9090, "grafana_port": 3000},
    ),
]


@router.get("/roles", response_model=RoleListResponse)
async def list_roles(
    _: Annotated[dict, Depends(get_current_user)],
) -> RoleListResponse:
    """List available roles for deployment."""
    return RoleListResponse(roles=AVAILABLE_ROLES)


@router.get("", response_model=DeploymentListResponse)
async def list_deployments(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> DeploymentListResponse:
    """List deployments with optional filters."""
    deployments, total = await deployment_service.list_deployments(
        db, node_id, status_filter, page, per_page
    )

    return DeploymentListResponse(
        deployments=deployments,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    deployment_data: DeploymentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> DeploymentResponse:
    """Create a new deployment."""
    role_names = {r.name for r in AVAILABLE_ROLES}
    invalid_roles = set(deployment_data.roles) - role_names

    if invalid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid roles: {', '.join(invalid_roles)}",
        )

    try:
        deployment = await deployment_service.create_deployment(
            db, deployment_data, triggered_by=current_user.get("sub", "unknown")
        )
        logger.info(
            "Deployment created: %s for node %s",
            deployment.deployment_id,
            deployment.node_id,
        )
        return deployment
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> DeploymentResponse:
    """Get a deployment by ID."""
    deployment = await deployment_service.get_deployment(db, deployment_id)

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )

    return deployment


@router.post("/{deployment_id}/cancel", response_model=DeploymentResponse)
async def cancel_deployment(
    deployment_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> DeploymentResponse:
    """Cancel a pending or running deployment."""
    try:
        deployment = await deployment_service.cancel_deployment(db, deployment_id)

        if not deployment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deployment not found",
            )

        logger.info("Deployment cancelled: %s", deployment_id)
        return deployment

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
