from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import logging
from datetime import datetime
import requests

from src.config import global_config_manager

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    """Health check endpoint for connection status monitoring"""
    try:
        # Check if we can connect to Ollama
        ollama_healthy = False
        try:
            ollama_check_url = global_config_manager.get_nested('backend.ollama_endpoint', 'http://localhost:11434/api/generate').replace('/api/generate', '/api/tags')
            response = requests.get(ollama_check_url, timeout=5)
            ollama_healthy = response.status_code == 200
        except:
            ollama_healthy = False

        # Check Redis connection
        redis_status = "disconnected"
        redis_search_module_loaded = False
        try:
            import redis
            # Get Redis config from centralized config
            task_transport_config = global_config_manager.get('task_transport', {})
            if task_transport_config.get('type') == 'redis':
                redis_config = task_transport_config.get('redis', {})
                redis_host = redis_config.get('host', 'localhost')
                redis_port = redis_config.get('port', 6379)

                redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
                redis_client.ping()
                redis_status = "connected"

                # Check if RediSearch module is loaded
                try:
                    modules = redis_client.module_list()
                    if modules and isinstance(modules, list):
                        redis_search_module_loaded = any(
                            (isinstance(module, dict) and module.get('name') == 'search') or
                            (isinstance(module, dict) and module.get(b'name') == b'search') or
                            (hasattr(module, '__getitem__') and (module.get('name') == 'search' or module.get(b'name') == b'search'))
                            for module in modules
                        )
                    else:
                        redis_search_module_loaded = False
                except:
                    # If we can't check modules, assume it's not loaded
                    redis_search_module_loaded = False
            else:
                redis_status = "not_configured"
        except Exception as e:
            logger.debug(f"Redis connection check failed: {str(e)}")
            redis_status = "disconnected"

        return {
            "status": "healthy",
            "backend": "connected",
            "ollama": "connected" if ollama_healthy else "disconnected",
            "redis_status": redis_status,
            "redis_search_module_loaded": redis_search_module_loaded,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "backend": "connected",
                "ollama": "unknown",
                "redis_status": "unknown",
                "redis_search_module_loaded": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

@router.post("/restart")
async def restart():
    try:
        logger.info("Restart request received")
        return {"status": "success", "message": "Restart initiated."}
    except Exception as e:
        logger.error(f"Error processing restart request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing restart request: {str(e)}")

@router.get("/models")
async def get_models():
    """Get available LLM models"""
    try:
        ollama_config = global_config_manager.get_nested('llm_config.ollama', {})
        models = ollama_config.get('models', {})
        
        # Try to get models from Ollama API
        try:
            ollama_host = ollama_config.get('host', 'http://localhost:11434')
            ollama_url = f"{ollama_host}/api/tags"
            response = requests.get(ollama_url, timeout=5)
            if response.status_code == 200:
                ollama_models = response.json().get('models', [])
                # Extract model names
                available_models = [model['name'] for model in ollama_models]
                return {
                    "status": "success",
                    "models": available_models,
                    "configured_models": models
                }
        except Exception as e:
            logger.warning(f"Could not fetch models from Ollama: {str(e)}")
            
        # Fallback to configured models
        return {
            "status": "success", 
            "models": list(models.values()),
            "configured_models": models
        }
    except Exception as e:
        logger.error(f"Error getting models: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Error getting models: {str(e)}"})

@router.get("/files")
async def list_files():
    """List files in the project directory"""
    try:
        import os
        base_dir = os.getcwd()
        files_list = []
        
        for item_name in os.listdir(base_dir):
            if item_name.startswith('.'):  # Skip hidden files
                continue
            item_path = os.path.join(base_dir, item_name)
            is_dir = os.path.isdir(item_path)
            files_list.append({
                "name": item_name,
                "path": item_name,
                "is_dir": is_dir,
                "size": os.path.getsize(item_path) if not is_dir else None,
                "last_modified": os.path.getmtime(item_path)
            })
        
        files_list.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return {"files": files_list}
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Error listing files: {str(e)}"})
