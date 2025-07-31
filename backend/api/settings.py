from fastapi import APIRouter, HTTPException
import logging

from backend.services.config_service import ConfigService

router = APIRouter()

logger = logging.getLogger(__name__)

@router.get("/")
async def get_settings():
    """Get application settings"""
    try:
        return ConfigService.get_settings()
    except Exception as e:
        logger.error(f"Error getting settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting settings: {str(e)}")

@router.post("/")
async def save_settings(settings_data: dict):
    """Save application settings"""
    try:
        result = ConfigService.save_settings(settings_data)
        return result
    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving settings: {str(e)}")

@router.get("/backend")
async def get_backend_settings():
    """Get backend-specific settings"""
    try:
        return ConfigService.get_backend_settings()
    except Exception as e:
        logger.error(f"Error getting backend settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting backend settings: {str(e)}")

@router.post("/backend")
async def save_backend_settings(backend_settings: dict):
    """Save backend-specific settings"""
    try:
        result = ConfigService.update_backend_settings(backend_settings)
        return result
    except Exception as e:
        logger.error(f"Error saving backend settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving backend settings: {str(e)}")

@router.get("/config")
async def get_full_config():
    """Get complete application configuration"""
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error(f"Error getting full config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting full config: {str(e)}")
