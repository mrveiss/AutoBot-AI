import logging

from fastapi import APIRouter, HTTPException

from backend.services.config_service import ConfigService
from backend.utils.connection_utils import ConnectionTester

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/config")
async def get_redis_config():
    """Get current Redis configuration"""
    try:
        return ConfigService.get_redis_config()
    except Exception as e:
        logger.error(f"Error getting Redis config: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting Redis config: {str(e)}"
        )


@router.post("/config")
async def update_redis_config(config_data: dict):
    """Update Redis configuration"""
    try:
        result = ConfigService.update_redis_config(config_data)
        return result
    except Exception as e:
        logger.error(f"Error updating Redis config: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating Redis config: {str(e)}"
        )


@router.post("/test_connection")
async def test_redis_connection():
    """Test Redis connection with current configuration"""
    try:
        result = ConnectionTester.test_redis_connection()
        return result
    except Exception as e:
        logger.error(f"Redis connection test failed: {str(e)}")
        return {
            "status": "disconnected",
            "message": f"Failed to connect to Redis: {str(e)}",
        }
