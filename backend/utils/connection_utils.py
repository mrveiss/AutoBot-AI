"""
Shared utilities for testing connections to various services.
Eliminates duplication across system.py, llm.py, and redis.py
"""
import logging
import requests
import redis
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from src.config import global_config_manager
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class ConnectionTester:
    """Centralized connection testing for all backend services"""
    
    @staticmethod
    async def test_ollama_connection() -> Dict[str, Any]:
        """Test Ollama LLM connection with current configuration"""
        try:
            # Get Ollama configuration from the correct paths
            # First try the new structure, then fall back to legacy structure
            ollama_endpoint = None
            ollama_model = None
            
            # Try new structure first
            llm_config = global_config_manager.get('backend', {}).get('llm', {})
            if llm_config.get('provider_type') == 'local' and llm_config.get('local', {}).get('provider') == 'ollama':
                ollama_providers = llm_config.get('local', {}).get('providers', {})
                ollama_config = ollama_providers.get('ollama', {})
                if ollama_config.get('endpoint'):
                    ollama_endpoint = ollama_config['endpoint']
                if ollama_config.get('selected_model'):
                    ollama_model = ollama_config['selected_model']
            
            # Fall back to legacy structure if new structure doesn't have the values
            if not ollama_endpoint:
                ollama_endpoint = global_config_manager.get_nested('backend.ollama_endpoint', 'http://localhost:11434/api/generate')
            if not ollama_model:
                ollama_model = global_config_manager.get_nested('backend.ollama_model', 'phi:2.7b')
            
            # Default fallbacks
            if not ollama_endpoint:
                ollama_endpoint = 'http://localhost:11434/api/generate'
            if not ollama_model:
                ollama_model = 'phi:2.7b'

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
            logger.error(f"Ollama connection test failed: {str(e)}")
            return {
                "status": "disconnected",
                "message": f"Failed to test Ollama connection: {str(e)}"
            }

    @staticmethod
    def test_redis_connection() -> Dict[str, Any]:
        """Test Redis connection with current configuration"""
        try:
            # First check task_transport config (backwards compatibility)
            task_transport_config = global_config_manager.get('task_transport', {})
            redis_config = None
            redis_host = None
            redis_port = None
            
            if task_transport_config.get('type') == 'redis':
                redis_config = task_transport_config.get('redis', {})
                redis_host = redis_config.get('host', 'localhost')
                redis_port = redis_config.get('port', 6379)
            else:
                # Check memory.redis config (current structure)
                memory_config = global_config_manager.get('memory', {})
                redis_config = memory_config.get('redis', {})
                
                if redis_config.get('enabled', False):
                    redis_host = redis_config.get('host', 'localhost')
                    redis_port = redis_config.get('port', 6379)
                else:
                    return {
                        "status": "not_configured",
                        "message": "Redis is not enabled in memory configuration"
                    }

            if not redis_host or not redis_port:
                return {
                    "status": "not_configured",
                    "message": "Redis configuration is incomplete (missing host or port)"
                }

            redis_client = get_redis_client()
            if redis_client is None:
                return {
                    "status": "not_configured", 
                    "message": "Redis client could not be initialized"
                }
            redis_client.ping()

            # Check if RediSearch module is loaded
            redis_search_module_loaded = False
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

            return {
                "status": "connected",
                "message": f"Successfully connected to Redis at {redis_host}:{redis_port}",
                "host": redis_host,
                "port": redis_port,
                "redis_search_module_loaded": redis_search_module_loaded
            }
        except Exception as e:
            logger.error(f"Redis connection test failed: {str(e)}")
            return {
                "status": "disconnected",
                "message": f"Failed to connect to Redis: {str(e)}"
            }

    @staticmethod
    async def get_comprehensive_health_status() -> Dict[str, Any]:
        """Get comprehensive health status for all services"""
        try:
            # Test Ollama
            ollama_status = await ConnectionTester.test_ollama_connection()
            ollama_healthy = ollama_status["status"] == "connected"

            # Test Redis
            redis_result = ConnectionTester.test_redis_connection()
            
            return {
                "status": "healthy",
                "backend": "connected",
                "ollama": "connected" if ollama_healthy else "disconnected",
                "redis_status": redis_result["status"],
                "redis_search_module_loaded": redis_result.get("redis_search_module_loaded", False),
                "timestamp": datetime.now().isoformat(),
                "details": {
                    "ollama": ollama_status,
                    "redis": redis_result
                }
            }
        except Exception as e:
            logger.error(f"Error in comprehensive health check: {str(e)}")
            return {
                "status": "unhealthy",
                "backend": "connected",
                "ollama": "unknown",
                "redis_status": "unknown",
                "redis_search_module_loaded": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }


class ModelManager:
    """Centralized model management for LLM services"""
    
    @staticmethod
    async def get_available_models() -> Dict[str, Any]:
        """Get list of available LLM models from all configured providers"""
        models = []
        
        try:
            # Get Ollama models
            ollama_models = await ModelManager._get_ollama_models()
            models.extend(ollama_models)
            
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
                "status": "success",
                "models": models,
                "total_count": len(models)
            }
        except Exception as e:
            logger.error(f"Error getting available models: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "models": [],
                "total_count": 0
            }

    @staticmethod
    async def _get_ollama_models() -> list:
        """Get models from Ollama service"""
        try:
            ollama_config = global_config_manager.get_nested('llm_config.ollama', {})
            ollama_host = ollama_config.get('host', 'http://localhost:11434')
            ollama_url = f"{ollama_host}/api/tags"
            
            response = requests.get(ollama_url, timeout=10)
            if response.status_code == 200:
                ollama_data = response.json()
                models = []
                if 'models' in ollama_data:
                    for model in ollama_data['models']:
                        models.append({
                            "name": model.get('name', 'Unknown'),
                            "type": "ollama",
                            "size": model.get('size', 0),
                            "modified_at": model.get('modified_at', ''),
                            "available": True
                        })
                return models
            return []
        except Exception as e:
            logger.warning(f"Failed to get Ollama models: {str(e)}")
            return []
