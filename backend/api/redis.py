from fastapi import APIRouter, HTTPException
import logging
import yaml
import os

from src.config import global_config_manager

router = APIRouter()

logger = logging.getLogger(__name__)

@router.get("/api/redis/config")
async def get_redis_config():
    """Get current Redis configuration"""
    try:
        task_transport_config = global_config_manager.get('task_transport', {})
        redis_config = task_transport_config.get('redis', {})

        return {
            "type": task_transport_config.get('type', 'local'),
            "host": redis_config.get('host', 'localhost'),
            "port": redis_config.get('port', 6379),
            "channels": redis_config.get('channels', {}),
            "priority": redis_config.get('priority', 10)
        }
    except Exception as e:
        logger.error(f"Error getting Redis config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting Redis config: {str(e)}")

@router.post("/api/redis/config")
async def update_redis_config(config_data: dict):
    """Update Redis configuration"""
    try:
        # Load current config
        current_config = global_config_manager.to_dict()

        # Update task transport configuration
        if 'task_transport' not in current_config:
            current_config['task_transport'] = {}

        # Update transport type
        if 'type' in config_data:
            current_config['task_transport']['type'] = config_data['type']

        # Update Redis-specific settings
        if 'task_transport' not in current_config:
            current_config['task_transport'] = {}
        if 'redis' not in current_config['task_transport']:
            current_config['task_transport']['redis'] = {}

        redis_config = current_config['task_transport']['redis']

        if 'host' in config_data:
            redis_config['host'] = config_data['host']
        if 'port' in config_data:
            redis_config['port'] = int(config_data['port'])
        if 'channels' in config_data:
            redis_config['channels'] = config_data['channels']
        if 'priority' in config_data:
            redis_config['priority'] = int(config_data['priority'])

        # Save updated config to file
        config_file_path = 'config/config.yaml'
        os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
        with open(config_file_path, 'w') as f:
            yaml.dump(current_config, f, default_flow_style=False)

        # Reload the global config manager
        global_config_manager.reload()

        logger.info(f"Updated Redis configuration: {config_data}")
        return {"status": "success", "message": "Redis configuration updated successfully"}
    except Exception as e:
        logger.error(f"Error updating Redis config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating Redis config: {str(e)}")

@router.post("/api/redis/test_connection")
async def test_redis_connection():
    """Test Redis connection with current configuration"""
    try:
        import redis
        task_transport_config = global_config_manager.get('task_transport', {})

        if task_transport_config.get('type') != 'redis':
            return {
                "status": "not_configured",
                "message": "Redis transport is not configured (type is not 'redis')"
            }

        redis_config = task_transport_config.get('redis', {})
        redis_host = redis_config.get('host', 'localhost')
        redis_port = redis_config.get('port', 6379)

        redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        redis_client.ping()

        # Check if RediSearch module is loaded
        redis_search_module_loaded = False
        try:
            modules = redis_client.module_list()
            redis_search_module_loaded = any(module[b'name'] == b'search' or module.get('name') == 'search' for module in modules)
        except:
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
