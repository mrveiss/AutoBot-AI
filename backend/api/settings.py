from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import json
import logging

from src.config import global_config_manager

router = APIRouter()

logger = logging.getLogger(__name__)

# Path for settings file
SETTINGS_FILE = "config/settings.json"

class Settings(BaseModel):
    settings: dict

@router.post("/settings")
async def save_settings(settings_data: Settings):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings_data.settings, f, indent=2)
        logger.info("Saved settings")
        # ConfigManager handles automatic reloading
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving settings: {str(e)}")

@router.get("/settings")
async def get_settings():
    try:
        result = {}
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                result = json.load(f)
        else:
            logger.info("No settings file found, returning empty dict")

        return result
    except Exception as e:
        logger.error(f"Error loading settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading settings: {str(e)}")

@router.post("/settings/backend")
async def update_backend_settings(settings_data: Settings):
    try:
        # Load current settings
        current_settings = {}
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                current_settings = json.load(f)

        # Update only backend-related settings
        if 'backend' in settings_data.settings:
            current_settings['backend'] = settings_data.settings['backend']
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(current_settings, f, indent=2)
            logger.info("Updated backend settings")
            # ConfigManager handles automatic reloading
            return {"status": "success"}
        else:
            logger.error("No backend settings provided")
            raise HTTPException(status_code=400, detail="No backend settings provided")
    except Exception as e:
        logger.error(f"Error updating backend settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating backend settings: {str(e)}")

@router.get("/settings/backend")
async def get_backend_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                return settings.get('backend', {})
        logger.info("No settings file found, returning empty dict for backend settings")
        return {}
    except Exception as e:
        logger.error(f"Error loading backend settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading backend settings: {str(e)}")
