# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

import logging
from datetime import datetime
from typing import Optional

from auth_middleware import auth_middleware
from backend.services.redis_service_manager import (
    RedisConnectionError,
    RedisServiceManager,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Redis Service Management"])

# Performance optimization: O(1) lookup for privileged roles (Issue #326)
PRIVILEGED_ROLES = {"admin", "operator"}

# Global service manager instance (singleton)
_service_manager: Optional[RedisServiceManager] = None
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
    user_data = auth_middleware.get_user_from_request(request)

    if not user_data:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Check if user has admin role
    if user_data.get("role") != "admin":
        raise HTTPException(
            status_code=403, detail="Admin role required for this operation"
        )

    return user_data.get("username", "unknown")


def check_operator_permission(request: Request) -> str:
    """
    Check if user has operator or admin permissions

    Returns:
        User ID if authorized

    Raises:
        HTTPException: If user lacks operator/admin permissions
    """
    user_data = auth_middleware.get_user_from_request(request)

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


# Pydantic models
class ServiceOperationResponse(BaseModel):
    """Service operation response"""

    success: bool
    operation: str = Field(..., description="Operation type: start, stop, restart")
    message: str
    duration_seconds: float
    timestamp: datetime
    new_status: str = Field(
        ..., description="New service status: running, stopped, failed, unknown"
    )
    error: Optional[str] = None


class ServiceStatusResponse(BaseModel):
    """Service status response"""

    status: str = Field(
        ..., description="Service status: running, stopped, failed, unknown"
    )
    pid: Optional[int] = None
    uptime_seconds: Optional[float] = None
    memory_mb: Optional[float] = None
    last_check: datetime


class HealthStatusResponse(BaseModel):
    """Health status response"""

    overall_status: str = Field(
        ..., description="Overall health: healthy, degraded, critical"
    )
    service_running: bool
    connectivity: bool
    response_time_ms: float
    last_successful_command: Optional[datetime] = None
    error_count_last_hour: int = 0
    recommendations: list = Field(default_factory=list)


# API Endpoints
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_redis_service",
    error_code_prefix="REDIS_SERVICE",
)
@router.post("/start", response_model=ServiceOperationResponse)
async def start_redis_service(
    request: Request, manager: RedisServiceManager = Depends(get_service_manager)
):
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
        raise HTTPException(
            status_code=503, detail=f"Cannot connect to Redis VM: {str(e)}"
        )
    except Exception as e:
        logger.error("Start service error: %s", e)
        raise HTTPException(status_code=500, detail=f"Service start failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_redis_service",
    error_code_prefix="REDIS_SERVICE",
)
@router.post("/stop", response_model=ServiceOperationResponse)
async def stop_redis_service(
    request: Request, manager: RedisServiceManager = Depends(get_service_manager)
):
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
        raise HTTPException(
            status_code=503, detail=f"Cannot connect to Redis VM: {str(e)}"
        )
    except Exception as e:
        logger.error("Stop service error: %s", e)
        raise HTTPException(status_code=500, detail=f"Service stop failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="restart_redis_service",
    error_code_prefix="REDIS_SERVICE",
)
@router.post("/restart", response_model=ServiceOperationResponse)
async def restart_redis_service(
    request: Request, manager: RedisServiceManager = Depends(get_service_manager)
):
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
        raise HTTPException(
            status_code=503, detail=f"Cannot connect to Redis VM: {str(e)}"
        )
    except Exception as e:
        logger.error("Restart service error: %s", e)
        raise HTTPException(status_code=500, detail=f"Service restart failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_status",
    error_code_prefix="REDIS_SERVICE",
)
@router.get("/status", response_model=ServiceStatusResponse)
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
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_health",
    error_code_prefix="REDIS_SERVICE",
)
@router.get("/health", response_model=HealthStatusResponse)
async def get_redis_health(manager: RedisServiceManager = Depends(get_service_manager)):
    """
    Get detailed Redis service health status

    No authentication required (public endpoint)
    """
    try:
        health = await manager.get_health()

        return HealthStatusResponse(
            overall_status=health.overall_status,
            service_running=health.service_running,
            connectivity=health.connectivity,
            response_time_ms=health.response_time_ms,
            last_successful_command=health.last_successful_command,
            error_count_last_hour=health.error_count_last_hour,
            recommendations=health.recommendations or [],
        )

    except Exception as e:
        logger.error("Get health error: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get health status: {str(e)}"
        )
