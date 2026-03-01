# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Deployments API Routes

Role definitions are sourced from role_registry.DEFAULT_ROLES (single
source of truth) so every view in the platform shows the same set of
roles.  See docs/developer/ROLES.md for the authoritative spec.
"""

import logging
from typing import Dict, List, Optional

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
from services.role_registry import DEFAULT_ROLES
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/deployments", tags=["deployments"])

# ---------------------------------------------------------------------------
# Role metadata derived from role_registry.DEFAULT_ROLES
#
# The registry owns role *names* and operational fields.  The mapping
# below adds UI-only fields (category, description, tools) that the
# deployment wizard needs.  When a role has no explicit entry it gets
# sensible defaults derived from the registry data.
# ---------------------------------------------------------------------------

_ROLE_UI_META: Dict[str, Dict] = {
    "slm-backend": {
        "description": "SLM backend API server",
        "category": "core",
        "tools": ["uvicorn", "python3", "pip", "alembic"],
    },
    "slm-frontend": {
        "description": "SLM Vue.js frontend",
        "category": "core",
        "tools": ["nginx", "node", "npm"],
    },
    "slm-database": {
        "description": "PostgreSQL 16 database server",
        "category": "core",
        "tools": ["postgresql", "psql", "pg_dump", "pg_restore"],
    },
    "slm-monitoring": {
        "description": "Prometheus and Grafana monitoring stack",
        "category": "observability",
        "tools": ["prometheus", "grafana", "node_exporter", "alertmanager"],
    },
    "backend": {
        "description": "AutoBot backend API server",
        "category": "application",
        "tools": ["uvicorn", "gunicorn", "python3", "pip"],
    },
    "celery": {
        "description": "Celery background task worker",
        "category": "application",
        "tools": ["celery", "python3"],
    },
    "frontend": {
        "description": "AutoBot Vue.js frontend server",
        "category": "application",
        "tools": ["nginx", "node", "npm", "vite"],
    },
    "redis": {
        "description": "Redis Stack server for data persistence",
        "category": "data",
        "tools": ["redis-server", "redis-cli", "redis-sentinel"],
    },
    "ai-stack": {
        "description": "AI tools and processing stack",
        "category": "ai",
        "tools": [
            "chromadb",
            "langchain",
            "transformers",
            "torch",
            "onnxruntime",
        ],
    },
    "chromadb": {
        "description": "ChromaDB vector database",
        "category": "ai",
        "tools": ["chromadb"],
    },
    "npu-worker": {
        "description": "Intel NPU acceleration worker",
        "category": "ai",
        "tools": ["openvino", "intel-npu-driver", "benchmark_app"],
    },
    "tts-worker": {
        "description": "Text-to-speech synthesis worker",
        "category": "ai",
        "tools": ["python3", "pip"],
    },
    "browser-service": {
        "description": "Playwright browser automation service",
        "category": "automation",
        "tools": ["playwright", "chromium", "firefox", "webkit"],
    },
    "autobot-llm-cpu": {
        "description": "LLM inference on CPU (Ollama)",
        "category": "ai",
        "tools": ["ollama"],
    },
    "autobot-llm-gpu": {
        "description": "LLM inference on GPU (Ollama)",
        "category": "ai",
        "tools": ["ollama"],
    },
    "autobot-shared": {
        "description": "Shared Python library (deployed to all nodes)",
        "category": "infrastructure",
        "tools": ["pip", "python3"],
    },
    "slm-agent": {
        "description": "SLM monitoring agent for node health reporting",
        "category": "infrastructure",
        "tools": ["systemd", "journalctl", "htop", "netstat"],
    },
    "vnc": {
        "description": "VNC remote desktop server with noVNC web interface",
        "category": "remote-access",
        "tools": [
            "tigervnc-standalone-server",
            "websockify",
            "novnc",
            "x11vnc",
        ],
    },
}


def _build_available_roles() -> List[RoleInfo]:
    """Build RoleInfo list from role_registry.DEFAULT_ROLES."""
    roles: List[RoleInfo] = []
    for reg in DEFAULT_ROLES:
        name = reg["name"]
        meta = _ROLE_UI_META.get(name, {})
        roles.append(
            RoleInfo(
                name=name,
                description=meta.get(
                    "description",
                    reg.get("display_name", name),
                ),
                category=meta.get("category", "core"),
                ansible_role=reg.get("ansible_playbook", ""),
                dependencies=[],
                variables={},
                tools=meta.get("tools", []),
            )
        )
    return roles


AVAILABLE_ROLES = _build_available_roles()


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
