# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import logging

from fastapi import APIRouter

from backend.services.config_service import ConfigService
from src.utils.catalog_http_exceptions import raise_server_error
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()

logger = logging.getLogger(__name__)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_settings",
    error_code_prefix="SETTINGS",
)
@router.get("/")
async def get_settings():
    """Get application settings - now uses full config from config.yaml"""
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error("Error getting settings: %s", str(e))
        raise_server_error("API_0003", f"Error getting settings: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_settings_explicit",
    error_code_prefix="SETTINGS",
)
@router.get("/settings")
async def get_settings_explicit():
    """Get application settings - explicit /settings endpoint for frontend compatibility"""
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error("Error getting settings: %s", str(e))
        raise_server_error("API_0003", f"Error getting settings: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_settings",
    error_code_prefix="SETTINGS",
)
@router.post("/")
async def save_settings(settings_data: dict):
    """Save application settings"""
    try:
        # Only save if there's actual data to save
        if not settings_data:
            logger.warning("Received empty settings data, skipping save")
            return {"status": "skipped", "message": "No data to save"}

        result = ConfigService.save_full_config(settings_data)
        return result
    except Exception as e:
        logger.error("Error saving settings: %s", str(e))
        raise_server_error("API_0003", f"Error saving settings: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_settings_explicit",
    error_code_prefix="SETTINGS",
)
@router.post("/settings")
async def save_settings_explicit(settings_data: dict):
    """Save application settings - explicit /settings endpoint for frontend compatibility"""
    try:
        # Only save if there's actual data to save
        if not settings_data:
            logger.warning("Received empty settings data, skipping save")
            return {"status": "skipped", "message": "No data to save"}

        result = ConfigService.save_full_config(settings_data)
        return result
    except Exception as e:
        logger.error("Error saving settings: %s", str(e))
        raise_server_error("API_0003", f"Error saving settings: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_backend_settings",
    error_code_prefix="SETTINGS",
)
@router.get("/backend")
async def get_backend_settings():
    """Get backend-specific settings"""
    try:
        return ConfigService.get_backend_settings()
    except Exception as e:
        logger.error("Error getting backend settings: %s", str(e))
        raise_server_error("API_0003", f"Error getting backend settings: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_backend_settings",
    error_code_prefix="SETTINGS",
)
@router.post("/backend")
async def save_backend_settings(backend_settings: dict):
    """Save backend-specific settings"""
    try:
        result = ConfigService.update_backend_settings(backend_settings)
        return result
    except Exception as e:
        logger.error("Error saving backend settings: %s", str(e))
        raise_server_error("API_0003", f"Error saving backend settings: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_full_config",
    error_code_prefix="SETTINGS",
)
@router.get("/config")
async def get_full_config():
    """Get complete application configuration"""
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error("Error getting full config: %s", str(e))
        raise_server_error("API_0003", f"Error getting full config: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_full_config",
    error_code_prefix="SETTINGS",
)
@router.post("/config")
async def save_full_config(config_data: dict):
    """Save complete application configuration to config.yaml"""
    try:
        # Save the complete configuration to config.yaml and reload
        result = ConfigService.save_full_config(config_data)
        return result
    except Exception as e:
        logger.error("Error saving full config: %s", str(e))
        raise_server_error("API_0003", f"Error saving full config: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_cache",
    error_code_prefix="SETTINGS",
)
@router.post("/clear-cache")
async def clear_cache():
    """Clear application cache - includes config cache"""
    try:
        logger.info("Settings clear-cache endpoint called - clearing config cache")

        # Clear the ConfigService cache to force reload of settings
        ConfigService.clear_cache()

        return {
            "status": "success",
            "message": (
                "Configuration cache cleared. Settings will be reloaded on next request."
            ),
            "available_endpoints": {
                "clear_all_redis": "/api/cache/redis/clear/all",
                "clear_specific_redis": "/api/cache/redis/clear/{database_name}",
                "clear_cache_type": "/api/cache/clear/{cache_type}",
            },
        }
    except Exception as e:
        logger.error("Error in clear-cache endpoint: %s", str(e))
        raise_server_error("API_0003", f"Error in clear-cache endpoint: {str(e)}")
