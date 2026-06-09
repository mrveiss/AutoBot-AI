# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

"""
Redis health, connection-status, and configuration endpoints.

Exposes diagnostic routes for inspecting Redis connectivity, memory usage,
and runtime configuration without direct redis-cli access.
"""

from fastapi import APIRouter, HTTPException

from api.schemas_system import (
    RedisConfigResponse,
    RedisConnectionStatusResponse,
)
from api.system_health import register_redis_probe
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.config_service import ConfigService
from utils.connection_utils import ConnectionTester

router = APIRouter()

logger = get_logger(__name__)


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


register_redis_probe("redis", database="main")
