# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from api.system_health import ComponentHealth, register_health_probe
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.redis_client import get_async_redis_client
from services.config_service import ConfigService
from utils.connection_utils import ConnectionTester
from api.schemas_system import (
    RedisConfigResponse,
    RedisConnectionStatusResponse,
    RedisHealthResponse,
)

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/config", response_model=RedisConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_config",
    error_code_prefix="REDIS",
)
async def get_redis_config():
    """Get current Redis configuration"""
    try:
        return ConfigService.get_redis_config()
    except Exception as e:
        logger.error("Error getting Redis config: %s", str(e))
        raise HTTPException(status_code=500, detail="Error getting Redis config")


@router.post("/config", response_model=RedisConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_redis_config",
    error_code_prefix="REDIS",
)
async def update_redis_config(config_data: dict):
    """Update Redis configuration"""
    try:
        result = ConfigService.update_redis_config(config_data)
        return result
    except Exception:
        logger.error("Error updating Redis config: %s", "Internal server error")
        raise HTTPException(status_code=500, detail="Error updating Redis config")


@router.get("/status", response_model=RedisConnectionStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_status",
    error_code_prefix="REDIS",
)
async def get_redis_status():
    """Get Redis connection status"""
    try:
        result = ConnectionTester.test_redis_connection()
        return result
    except Exception:
        logger.error("Redis status check failed: %s", "Internal server error")
        return {
            "status": "disconnected",
            "message": "Failed to connect to Redis",
        }


@router.post("/test_connection", response_model=RedisConnectionStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_redis_connection",
    error_code_prefix="REDIS",
)
async def test_redis_connection():
    """Test Redis connection with current configuration"""
    try:
        result = ConnectionTester.test_redis_connection()
        return result
    except Exception:
        logger.error("Redis connection test failed: %s", "Internal server error")
        return {
            "status": "disconnected",
            "message": "Failed to connect to Redis",
        }


@register_health_probe("redis")
async def probe_redis(
    request: Optional[Request] = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for Redis connectivity.

    Uses the async client + ``await client.ping()`` so the probe never blocks
    the asyncio event loop. The legacy ``ConnectionTester.test_redis_connection``
    helper is sync; calling it from an async probe stalls every other probe in
    ``asyncio.gather``.
    """
    try:
        client = await get_async_redis_client(database="main")
        if client is None:
            return ComponentHealth(
                name="redis", status="down", detail="redis client unavailable"
            )
        await client.ping()
        return ComponentHealth(name="redis", status="ok")
    except Exception as exc:
        return ComponentHealth(
            name="redis",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )


@router.get("/health", response_model=RedisHealthResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_health",
    error_code_prefix="REDIS",
)
async def get_redis_health():
    """Get Redis health status for frontend health checks"""
    try:
        result = ConnectionTester.test_redis_connection()
        return {
            "status": "healthy" if result.get("status") == "connected" else "unhealthy",
            "redis_status": result.get("status"),
            "message": result.get("message"),
            "host": result.get("host"),
            "port": result.get("port"),
            "redis_search_module_loaded": result.get(
                "redis_search_module_loaded", False
            ),
        }
    except Exception:
        logger.error("Redis health check failed: %s", "Internal server error")
        return {
            "status": "unhealthy",
            "redis_status": "disconnected",
            "message": "Failed to check Redis health",
        }
