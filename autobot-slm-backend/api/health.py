# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from services.frontend_bundle_health import frontend_bundle_status

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

START_TIME = time.time()
VERSION = "1.0.0"


async def _check_redis_health() -> str:
    """Actively probe the 'main' Redis database (#14299).

    A backend whose circuit breaker is open on its primary datastore was
    invisible to every roll-up — this node stayed `online` and this very
    endpoint answered "healthy" purely because it never looked at Redis at
    all. ``get_async_redis_client`` goes through the SAME circuit breaker
    ``get_async_client`` does, so once a config/connection error has opened
    it (see ``connection_manager._check_circuit_breaker``), this returns
    immediately without re-attempting a connection or re-logging — it is not
    an extra source of the retry-storm #14299 also reports.
    """
    try:
        from autobot_shared.redis_client import get_async_redis_client, get_redis_health

        client = await get_async_redis_client(database="main")
        if client is not None:
            return "healthy"

        # #14299: distinguish "resolved to nothing configured" (a config
        # error — REDIS_HOST/vm.redis needs to be set, will not fix itself)
        # from every other reason get_async_redis_client can return None
        # (Redis disabled, or a genuine connection failure). A bare
        # "unhealthy" collapses both into one status an operator cannot act
        # on without reading the backend's own logs.
        last_error = str(
            get_redis_health().get("databases", {}).get("main", {}).get("metrics", {}).get("last_error", "")
        )
        if "configuration error" in last_error:
            return "unhealthy: redis configuration error — see backend logs"
        return "unhealthy"
    except Exception as exc:
        logger.error("Redis health check failed: %s", exc)
        return "unhealthy"


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HealthResponse:
    """Public health check endpoint."""
    try:
        online_count = await db.execute(select(func.count(Node.id)).where(Node.status == NodeStatus.ONLINE.value))
        total_count = await db.execute(select(func.count(Node.id)))

        nodes_online = online_count.scalar() or 0
        nodes_total = total_count.scalar() or 0
        db_status = "healthy"
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        nodes_online = 0
        nodes_total = 0
        db_status = "unhealthy"

    redis_status = await _check_redis_health()
    # #15462: a filesystem stat, so it stays cheap enough for a public endpoint
    # polled by monitoring — no thread hop needed.
    frontend_status = frontend_bundle_status()

    # #15462: `not_applicable` (this node serves no UI) is not a fault, so it
    # does not degrade the response — only a bundle that should be servable and
    # is not.
    frontend_ok = frontend_status.startswith(("healthy", "not_applicable"))
    healthy = db_status == "healthy" and redis_status == "healthy" and frontend_ok
    return HealthResponse(
        status="healthy" if healthy else "degraded",
        version=VERSION,
        uptime_seconds=time.time() - START_TIME,
        database=db_status,
        redis=redis_status,
        frontend=frontend_status,
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
