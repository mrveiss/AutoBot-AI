from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import logging
from datetime import datetime
import requests

from src.config import global_config_manager

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/api/health")
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
                    redis_search_module_loaded = any(module[b'name'] == b'search' or module.get('name') == 'search' for module in modules)
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

@router.post("/api/restart")
async def restart():
    try:
        logger.info("Restart request received")
        return {"status": "success", "message": "Restart initiated."}
    except Exception as e:
        logger.error(f"Error processing restart request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing restart request: {str(e)}")
