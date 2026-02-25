# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import logging

from fastapi import APIRouter, HTTPException
from services.config_service import ConfigService
from utils.connection_utils import ConnectionTester

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()

logger = logging.getLogger(__name__)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_config",
    error_code_prefix="REDIS",
)
@router.get("/config")
async def get_redis_config():
    """Get current Redis configuration"""
    try:
        return ConfigService.get_redis_config()
    except Exception as e:
        logger.error("Error getting Redis config: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error getting Redis config: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_redis_config",
    error_code_prefix="REDIS",
)
@router.post("/config")
async def update_redis_config(config_data: dict):
    """Update Redis configuration"""
    try:
        result = ConfigService.update_redis_config(config_data)
        return result
    except Exception as e:
        logger.error("Error updating Redis config: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error updating Redis config: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_status",
    error_code_prefix="REDIS",
)
@router.get("/status")
async def get_redis_status():
    """Get Redis connection status"""
    try:
        result = ConnectionTester.test_redis_connection()
        return result
    except Exception as e:
        logger.error("Redis status check failed: %s", str(e))
        return {
            "status": "disconnected",
            "message": f"Failed to connect to Redis: {str(e)}",
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_redis_connection",
    error_code_prefix="REDIS",
)
@router.post("/test_connection")
async def test_redis_connection():
    """Test Redis connection with current configuration"""
    try:
        result = ConnectionTester.test_redis_connection()
        return result
    except Exception as e:
        logger.error("Redis connection test failed: %s", str(e))
        return {
            "status": "disconnected",
            "message": f"Failed to connect to Redis: {str(e)}",
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_health",
    error_code_prefix="REDIS",
)
@router.get("/health")
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
    except Exception as e:
        logger.error("Redis health check failed: %s", str(e))
        return {
            "status": "unhealthy",
            "redis_status": "disconnected",
            "message": f"Failed to check Redis health: {str(e)}",
        }
