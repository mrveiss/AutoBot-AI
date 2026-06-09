# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Redis Service Management API
Provides endpoints for managing Redis service lifecycle on Redis VM

Features:
- Service control operations (start/stop/restart)
- Service status and health monitoring
- RBAC enforcement (admin/operator roles)
- Audit logging for all operations
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas_system import (
    ServiceOperationResponse,
    ServiceStatusResponse,
)
from api.system_health import ComponentHealth, register_health_probe
from auth_middleware import get_auth_middleware
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.redis_service_manager import RedisConnectionError, RedisServiceManager

logger = get_logger(__name__)
router = APIRouter(tags=["Redis Service Management"])

# Performance optimization: O(1) lookup for privileged roles (Issue #326)
PRIVILEGED_ROLES = {"admin", "operator"}

# Global service manager instance (singleton)
_service_manager: RedisServiceManager | None = None
_service_manager_started: bool = False


# Thread-safe lock for singleton
import asyncio as _asyncio_lock

_service_manager_lock = _asyncio_lock.Lock()


async def get_service_manager() -> RedisServiceManager:
    """
    Get the singleton Redis Service Manager instance (thread-safe).

    Uses singleton pattern to avoid creating multiple instances and maintain
    consistent state (error tracking, status cache) across requests.
    """
    global _service_manager, _service_manager_started

    if _service_manager is None:
        async with _service_manager_lock:
            # Double-check after acquiring lock
            if _service_manager is None:
                _service_manager = RedisServiceManager()
                logger.info("Created Redis Service Manager singleton instance")

    if not _service_manager_started:
        async with _service_manager_lock:
            # Double-check after acquiring lock
            if not _service_manager_started:
                await _service_manager.start()
                _service_manager_started = True
                logger.info("Started Redis Service Manager singleton")

    return _service_manager


def check_admin_permission(request: Request) -> str:
    """
    Check if user has admin permissions

    Returns:
        User ID if authorized

    Raises:
        HTTPException: If user lacks admin permissions
    """
    user_data = get_auth_middleware().get_user_from_request(request)

    if not user_data:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Check if user has admin role
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for this operation")

    return user_data.get("username", "unknown")


def check_operator_permission(request: Request) -> str:
    """
    Check if user has operator or admin permissions

    Returns:
        User ID if authorized

    Raises:
        HTTPException: If user lacks operator/admin permissions
    """
    user_data = get_auth_middleware().get_user_from_request(request)

    if not user_data:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Check if user has admin or operator role
    role = user_data.get("role", "")
    if role not in PRIVILEGED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Admin or operator role required for this operation",
        )

    return user_data.get("username", "unknown")


# API Endpoints
@router.post("/start", response_model=ServiceOperationResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_redis_service",
    error_code_prefix="REDIS_SERVICE",
)
async def start_redis_service(request: Request, manager: RedisServiceManager = Depends(get_service_manager)):
    """
    Start Redis service on Redis VM

    Requires: Admin or operator role
    """
    try:
        # Check permissions
        user_id = check_operator_permission(request)

        logger.info("Starting Redis service, requested by user: %s", user_id)

        # Execute start operation
        result = await manager.start_service(user_id=user_id)

        return ServiceOperationResponse(
            success=result.success,
            operation=result.operation,
            message=result.message,
            duration_seconds=result.duration_seconds,
            timestamp=result.timestamp,
            new_status=result.new_status,
            error=result.error,
        )

    except HTTPException:
        raise
    except RedisConnectionError as e:
        logger.error("Redis connection error: %s", e)
        raise HTTPException(status_code=503, detail="Cannot connect to Redis VM")
    except Exception as e:
        logger.error("Start service error: %s", e)
        raise HTTPException(status_code=500, detail="Service start failed")


@router.post("/stop", response_model=ServiceOperationResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_redis_service",
    error_code_prefix="REDIS_SERVICE",
)
async def stop_redis_service(request: Request, manager: RedisServiceManager = Depends(get_service_manager)):
    """
    Stop Redis service on Redis VM

    Requires: Admin role only

    Warning: Stopping Redis will affect all dependent services
    """
    try:
        # Check permissions (admin only for stop)
        user_id = check_admin_permission(request)

        logger.warning("Stopping Redis service, requested by admin: %s", user_id)

        # Execute stop operation
        result = await manager.stop_service(user_id=user_id)

        return ServiceOperationResponse(
            success=result.success,
            operation=result.operation,
            message=result.message,
            duration_seconds=result.duration_seconds,
            timestamp=result.timestamp,
            new_status=result.new_status,
            error=result.error,
        )

    except HTTPException:
        raise
    except RedisConnectionError as e:
        logger.error("Redis connection error: %s", e)
        raise HTTPException(status_code=503, detail="Cannot connect to Redis VM")
    except Exception as e:
        logger.error("Stop service error: %s", e)
        raise HTTPException(status_code=500, detail="Service stop failed")


@router.post("/restart", response_model=ServiceOperationResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="restart_redis_service",
    error_code_prefix="REDIS_SERVICE",
)
async def restart_redis_service(request: Request, manager: RedisServiceManager = Depends(get_service_manager)):
    """
    Restart Redis service on Redis VM

    Requires: Admin or operator role
    """
    try:
        # Check permissions
        user_id = check_operator_permission(request)

        logger.info("Restarting Redis service, requested by user: %s", user_id)

        # Execute restart operation
        result = await manager.restart_service(user_id=user_id)

        return ServiceOperationResponse(
            success=result.success,
            operation=result.operation,
            message=result.message,
            duration_seconds=result.duration_seconds,
            timestamp=result.timestamp,
            new_status=result.new_status,
            error=result.error,
        )

    except HTTPException:
        raise
    except RedisConnectionError as e:
        logger.error("Redis connection error: %s", e)
        raise HTTPException(status_code=503, detail="Cannot connect to Redis VM")
    except Exception as e:
        logger.error("Restart service error: %s", e)
        raise HTTPException(status_code=500, detail="Service restart failed")


@router.get("/status", response_model=ServiceStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_status",
    error_code_prefix="REDIS_SERVICE",
)
async def get_redis_status(manager: RedisServiceManager = Depends(get_service_manager)):
    """
    Get current Redis service status

    No authentication required (public endpoint)
    """
    try:
        status = await manager.get_service_status()

        return ServiceStatusResponse(
            status=status.status,
            pid=status.pid,
            uptime_seconds=status.uptime_seconds,
            memory_mb=status.memory_mb,
            last_check=status.last_check,
        )

    except Exception as e:
        logger.error("Get status error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get status")


@register_health_probe("redis_service")
async def probe_redis_service(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for Redis service-manager health."""
    try:
        manager = await get_service_manager()
        health = await manager.get_health()
        overall = (health.overall_status or "").lower()
        if overall in ("healthy", "ok"):
            return ComponentHealth(name="redis_service", status="ok")
        if overall in ("degraded", "warning"):
            return ComponentHealth(
                name="redis_service",
                status="degraded",
                detail=health.overall_status,
            )
        return ComponentHealth(
            name="redis_service",
            status="down",
            detail=health.overall_status or "service unhealthy",
        )
    except Exception as exc:
        return ComponentHealth(
            name="redis_service",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )
