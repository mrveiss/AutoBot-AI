# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Health API Routes
"""

import logging
import os
import time

import psutil
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Node, NodeStatus
from models.schemas import HealthResponse, SystemMetrics
from services.auth import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

START_TIME = time.time()
VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HealthResponse:
    """Public health check endpoint."""
    try:
        online_count = await db.execute(
            select(func.count(Node.id)).where(Node.status == NodeStatus.ONLINE.value)
        )
        total_count = await db.execute(select(func.count(Node.id)))

        nodes_online = online_count.scalar() or 0
        nodes_total = total_count.scalar() or 0
        db_status = "healthy"
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        nodes_online = 0
        nodes_total = 0
        db_status = "unhealthy"

    return HealthResponse(
        status="healthy" if db_status == "healthy" else "degraded",
        version=VERSION,
        uptime_seconds=time.time() - START_TIME,
        database=db_status,
        nodes_online=nodes_online,
        nodes_total=nodes_total,
    )


@router.get("/metrics", response_model=SystemMetrics)
async def system_metrics(
    _: Annotated[dict, Depends(get_current_user)],
) -> SystemMetrics:
    """Get system metrics (authenticated)."""
    return SystemMetrics(
        cpu_percent=psutil.cpu_percent(interval=0.1),
        memory_percent=psutil.virtual_memory().percent,
        disk_percent=psutil.disk_usage("/").percent,
        load_average=list(os.getloadavg()) if hasattr(os, "getloadavg") else [0, 0, 0],
    )


@router.get("/ready")
async def readiness_check(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Kubernetes-style readiness probe."""
    try:
        await db.execute(select(1))
        return {"status": "ready"}
    except Exception:
        return {"status": "not_ready"}


@router.get("/live")
async def liveness_check() -> dict:
    """Kubernetes-style liveness probe."""
    return {"status": "alive"}


@router.get("/health/database")
async def database_health_check() -> dict:
    """Detailed database health check endpoint (#786)."""
    from services.database import db_service

    return await db_service.health_check()
