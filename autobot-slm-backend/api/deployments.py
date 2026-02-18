# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Deployments API Routes
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/deployments", tags=["deployments"])

AVAILABLE_ROLES = [
    RoleInfo(
        name="autobot-slm-agent",
        description="SLM monitoring agent for node health reporting",
        category="core",
        ansible_role="slm_agent",
        dependencies=[],
        variables={"heartbeat_interval": 30},
        tools=["systemd", "journalctl", "htop", "netstat"],
    ),
    RoleInfo(
        name="autobot-database",
        description="Redis Stack server for data persistence",
        category="data",
        ansible_role="redis",
        dependencies=["autobot-slm-agent"],
        variables={"port": 6379, "cluster_enabled": False},
        tools=["redis-server", "redis-cli", "redis-sentinel"],
    ),
    RoleInfo(
        name="autobot-backend",
        description="AutoBot backend API server",
        category="application",
        ansible_role="backend",
        dependencies=["autobot-slm-agent", "autobot-database"],
        variables={"port": 8443, "workers": 4},
        tools=["uvicorn", "gunicorn", "python3", "pip"],
    ),
    RoleInfo(
        name="autobot-frontend",
        description="AutoBot Vue.js frontend server",
        category="application",
        ansible_role="frontend",
        dependencies=["autobot-slm-agent"],
        variables={"port": 443},
        tools=["nginx", "node", "npm", "vite"],
    ),
    RoleInfo(
        name="llm",
        description="LLM inference provider (Ollama/vLLM)",
        category="ai",
        ansible_role="llm",
        dependencies=["autobot-slm-agent"],
        variables={"port": 11434},
        tools=["ollama", "vllm", "llama-cpp"],
    ),
    RoleInfo(
        name="autobot-ai-stack",
        description="AI tools and processing stack",
        category="ai",
        ansible_role="ai-stack",
        dependencies=["autobot-slm-agent"],
        variables={"port": 8080},
        tools=["chromadb", "langchain", "transformers", "torch", "onnxruntime"],
    ),
    RoleInfo(
        name="autobot-npu-worker",
        description="Intel NPU acceleration worker",
        category="ai",
        ansible_role="npu-worker",
        dependencies=["autobot-slm-agent"],
        variables={"device_id": 0},
        tools=["openvino", "intel-npu-driver", "benchmark_app"],
    ),
    RoleInfo(
        name="autobot-browser-worker",
        description="Playwright browser automation service",
        category="automation",
        ansible_role="browser",
        dependencies=["autobot-slm-agent"],
        variables={"headless": True},
        tools=["playwright", "chromium", "firefox", "webkit"],
    ),
    RoleInfo(
        name="autobot-monitoring",
        description="Prometheus and Grafana monitoring stack",
        category="observability",
        ansible_role="monitoring",
        dependencies=["autobot-slm-agent"],
        variables={"prometheus_port": 9090, "grafana_port": 3000},
        tools=["prometheus", "grafana", "node_exporter", "alertmanager"],
    ),
    RoleInfo(
        name="vnc",
        description="VNC remote desktop server with noVNC web interface",
        category="remote-access",
        ansible_role="vnc",
        dependencies=["autobot-slm-agent"],
        variables={
            "websockify_enabled": True,
            "security_type": "VeNCrypt",
        },
        tools=["tigervnc-standalone-server", "websockify", "novnc", "x11vnc"],
    ),
    RoleInfo(
        name="autobot-slm-database",
        description="PostgreSQL 16 database server",
        category="data",
        ansible_role="postgresql",
        dependencies=["autobot-slm-agent"],
        variables={"postgresql_port": 5432, "postgresql_version": "16"},
        tools=["postgresql", "psql", "pg_dump", "pg_restore"],
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


@router.post("/{deployment_id}/rollback", response_model=DeploymentResponse)
async def rollback_deployment(
    deployment_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> DeploymentResponse:
    """Rollback a completed deployment."""
    try:
        deployment = await deployment_service.rollback_deployment(db, deployment_id)

        if not deployment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deployment not found",
            )

        logger.info("Deployment rollback initiated: %s", deployment_id)
        return deployment

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{deployment_id}/retry", response_model=DeploymentResponse)
async def retry_deployment(
    deployment_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> DeploymentResponse:
    """Retry a failed deployment."""
    try:
        deployment = await deployment_service.retry_deployment(
            db, deployment_id, triggered_by=current_user.get("sub", "unknown")
        )

        if not deployment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deployment not found",
            )

        logger.info("Deployment retry initiated: %s", deployment_id)
        return deployment

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
