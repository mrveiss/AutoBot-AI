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

@router.post("/")
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

@router.get("/")
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

@router.post("/backend")
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

@router.get("/backend")
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

@router.get("/config")
async def get_config_settings():
    """Get settings directly from config.yaml"""
    try:
        # Get the full configuration from the global config manager
        config_data = {
            'backend': {
                'server_host': global_config_manager.get_nested('backend.server_host', '0.0.0.0'),
                'server_port': global_config_manager.get_nested('backend.server_port', 8001),
                'chat_data_dir': global_config_manager.get_nested('backend.chat_data_dir', 'data/chats'),
                'cors_origins': global_config_manager.get_nested('backend.cors_origins', []),
                'llm': {
                    'provider_type': 'local',  # Always local for this config
                    'local': {
                        'provider': 'ollama',  # Primary provider from config
                        'providers': {
                            'ollama': {
                                'endpoint': global_config_manager.get_nested('llm_config.ollama.host', 'http://localhost:11434') + '/api/generate',
                                'host': global_config_manager.get_nested('llm_config.ollama.host', 'http://localhost:11434'),
                                'models': [],  # Will be loaded dynamically
                                'configured_models': global_config_manager.get_nested('llm_config.ollama.models', {}),
                                'selected_model': global_config_manager.get_nested('llm_config.default_llm', 'ollama_tinyllama')
                            }
                        }
                    }
                }
            },
            'memory': {
                'redis': {
                    'enabled': global_config_manager.get_nested('memory.redis.enabled', False),
                    'host': global_config_manager.get_nested('memory.redis.host', 'localhost'),
                    'port': global_config_manager.get_nested('memory.redis.port', 6379)
                }
            },
            'data': global_config_manager.get_nested('data', {}),
            'hardware_acceleration': global_config_manager.get_nested('hardware_acceleration', {})
        }
        
        # If provider is local (Ollama), dynamically load available models
        if config_data['backend']['llm']['provider_type'] == 'local':
            try:
                import requests
                ollama_host = global_config_manager.get_nested('llm_config.ollama.host', 'http://localhost:11434')
                response = requests.get(f"{ollama_host}/api/tags", timeout=5)
                if response.status_code == 200:
                    models_data = response.json()
                    available_models = [model['name'] for model in models_data.get('models', [])]
                    config_data['backend']['llm']['local']['providers']['ollama']['models'] = available_models
                    logger.info(f"Dynamically loaded {len(available_models)} Ollama models")
                else:
                    logger.warning(f"Could not fetch models from Ollama: HTTP {response.status_code}")
            except Exception as e:
                logger.warning(f"Error fetching Ollama models: {str(e)}")
                config_data['backend']['llm']['local']['providers']['ollama']['models'] = []
        
        return config_data
    except Exception as e:
        logger.error(f"Error loading config settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading config settings: {str(e)}")
