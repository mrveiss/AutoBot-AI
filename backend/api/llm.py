from fastapi import APIRouter, HTTPException
import logging
import yaml
import os
import requests
import json

from src.config import global_config_manager

router = APIRouter()

logger = logging.getLogger(__name__)

@router.get("/config")
async def get_llm_config():
    """Get current LLM configuration"""
    try:
        llm_config = global_config_manager.get('llm_config', {})
        backend_config = global_config_manager.get('backend', {})

        # Get default values from config with fallbacks
        default_llm_fallback = global_config_manager.get_nested('defaults.llm.default_llm', 'ollama_tinyllama')
        task_llm_fallback = global_config_manager.get_nested('defaults.llm.task_llm', 'ollama_tinyllama')
        ollama_endpoint_fallback = global_config_manager.get_nested('defaults.llm.ollama.endpoint', 'http://localhost:11434/api/generate')
        ollama_model_fallback = global_config_manager.get_nested('defaults.llm.ollama.model', 'tinyllama:latest')
        ollama_host_fallback = global_config_manager.get_nested('defaults.llm.ollama.host', 'http://localhost:11434')

        return {
            "default_llm": llm_config.get('default_llm', default_llm_fallback),
            "task_llm": llm_config.get('task_llm', task_llm_fallback),
            "ollama": {
                "endpoint": backend_config.get('ollama_endpoint', ollama_endpoint_fallback),
                "model": backend_config.get('ollama_model', ollama_model_fallback),
                "host": llm_config.get('ollama', {}).get('host', ollama_host_fallback),
                "models": llm_config.get('ollama', {}).get('models', {})
            },
            "openai": llm_config.get('openai', {}),
            "orchestrator_llm_settings": llm_config.get('orchestrator_llm_settings', {}),
            "task_llm_settings": llm_config.get('task_llm_settings', {})
        }
    except Exception as e:
        logger.error(f"Error getting LLM config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting LLM config: {str(e)}")

@router.post("/config")
async def update_llm_config(config_data: dict):
    """Update LLM configuration"""
    try:
        # Load current config
        current_config = global_config_manager.to_dict()

        # Update LLM configuration
        if 'llm_config' not in current_config:
            current_config['llm_config'] = {}
        if 'backend' not in current_config:
            current_config['backend'] = {}

        llm_config = current_config['llm_config']
        backend_config = current_config['backend']

        # Update basic LLM settings
        if 'default_llm' in config_data:
            llm_config['default_llm'] = config_data['default_llm']
        if 'task_llm' in config_data:
            llm_config['task_llm'] = config_data['task_llm']

        # Update Ollama settings
        if 'ollama' in config_data:
            ollama_data = config_data['ollama']
            if 'ollama' not in llm_config:
                llm_config['ollama'] = {}

            if 'endpoint' in ollama_data:
                backend_config['ollama_endpoint'] = ollama_data['endpoint']
            if 'model' in ollama_data:
                backend_config['ollama_model'] = ollama_data['model']
            if 'host' in ollama_data:
                llm_config['ollama']['host'] = ollama_data['host']
            if 'models' in ollama_data:
                llm_config['ollama']['models'] = ollama_data['models']

        # Update OpenAI settings
        if 'openai' in config_data:
            llm_config['openai'] = config_data['openai']

        # Update orchestrator and task LLM settings
        if 'orchestrator_llm_settings' in config_data:
            llm_config['orchestrator_llm_settings'] = config_data['orchestrator_llm_settings']
        if 'task_llm_settings' in config_data:
            llm_config['task_llm_settings'] = config_data['task_llm_settings']

        # Save updated config to file
        config_file_path = 'config/config.yaml'
        os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
        with open(config_file_path, 'w') as f:
            yaml.dump(current_config, f, default_flow_style=False)

        # Reload the global config manager
        global_config_manager.reload()

        logger.info(f"Updated LLM configuration: {config_data}")
        return {"status": "success", "message": "LLM configuration updated successfully"}
    except Exception as e:
        logger.error(f"Error updating LLM config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating LLM config: {str(e)}")

@router.post("/test_connection")
async def test_llm_connection():
    """Test LLM connection with current configuration"""
    try:
        # Get default values from config
        ollama_endpoint_fallback = global_config_manager.get_nested('defaults.llm.ollama.endpoint', 'http://localhost:11434/api/generate')
        ollama_model_fallback = global_config_manager.get_nested('defaults.llm.ollama.model', 'tinyllama:latest')
        
        ollama_endpoint = global_config_manager.get_nested('backend.ollama_endpoint', ollama_endpoint_fallback)
        ollama_model = global_config_manager.get_nested('backend.ollama_model', ollama_model_fallback)

        # Test Ollama connection
        ollama_check_url = ollama_endpoint.replace('/api/generate', '/api/tags')
        response = requests.get(ollama_check_url, timeout=10)

        if response.status_code == 200:
            # Test a simple generation request
            test_payload = {
                "model": ollama_model,
                "prompt": "Test connection - respond with 'OK'",
                "stream": False
            }

            test_response = requests.post(ollama_endpoint, json=test_payload, timeout=30)

            if test_response.status_code == 200:
                result = test_response.json()
                return {
                    "status": "connected",
                    "message": f"Successfully connected to Ollama with model '{ollama_model}'",
                    "endpoint": ollama_endpoint,
                    "model": ollama_model,
                    "test_response": result.get('response', 'No response text')[:100] + '...' if result.get('response') else 'No response'
                }
            else:
                return {
                    "status": "partial",
                    "message": f"Connected to Ollama but model '{ollama_model}' failed to respond",
                    "endpoint": ollama_endpoint,
                    "model": ollama_model,
                    "error": test_response.text
                }
        else:
            return {
                "status": "disconnected",
                "message": f"Failed to connect to Ollama at {ollama_check_url}",
                "endpoint": ollama_endpoint,
                "status_code": response.status_code
            }
    except Exception as e:
        logger.error(f"LLM connection test failed: {str(e)}")
        return {
            "status": "disconnected",
            "message": f"Failed to test LLM connection: {str(e)}"
        }

@router.get("/models")
async def get_available_llm_models():
    """Get list of available LLM models"""
    try:
        # Get default values from config
        ollama_endpoint_fallback = global_config_manager.get_nested('defaults.llm.ollama.endpoint', 'http://localhost:11434/api/generate')
        ollama_endpoint = global_config_manager.get_nested('backend.ollama_endpoint', ollama_endpoint_fallback)
        models = []

        # Get Ollama models
        try:
            ollama_tags_url = ollama_endpoint.replace('/api/generate', '/api/tags')
            response = requests.get(ollama_tags_url, timeout=10)
            if response.status_code == 200:
                ollama_data = response.json()
                if 'models' in ollama_data:
                    for model in ollama_data['models']:
                        models.append({
                            "name": model.get('name', 'Unknown'),
                            "type": "ollama",
                            "size": model.get('size', 0),
                            "modified_at": model.get('modified_at', ''),
                            "available": True
                        })
        except Exception as e:
            logger.warning(f"Failed to get Ollama models: {str(e)}")

        # Add configured models from config
        llm_config = global_config_manager.get('llm_config', {})
        ollama_config_models = llm_config.get('ollama', {}).get('models', {})
        for key, model_name in ollama_config_models.items():
            if not any(m['name'] == model_name for m in models):
                models.append({
                    "name": model_name,
                    "type": "ollama",
                    "configured": True,
                    "available": False
                })

        return {
            "models": models,
            "total_count": len(models)
        }
    except Exception as e:
        logger.error(f"Error getting available models: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting available models: {str(e)}")
