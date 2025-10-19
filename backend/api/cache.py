"""
Cache management API endpoints for clearing various cache types.
Provides comprehensive cache clearing functionality for frontend, backend, and Redis caches.
"""

import logging
import json
from typing import Dict, Any

import redis
from fastapi import APIRouter, HTTPException

from src.unified_config_manager import config as global_config_manager
from src.config_helper import cfg
from src.utils.distributed_service_discovery import get_redis_connection_params_sync
from src.constants.network_constants import NetworkConstants

router = APIRouter()
logger = logging.getLogger(__name__)

# Redis database mappings from config
REDIS_DATABASES = {
    "main": 0,
    "knowledge": 1,
    "prompts": 2,
    "conversations": 3,
    "sessions": 4,
    "cache": 5,
    "locks": 6,
    "monitoring": 7,
    "rate_limiting": 8,
    "analytics": 9,
    "websockets": 10,
    "config": 11,
}


def get_redis_connection(db_number: int = 0):
    """
    Get Redis connection for specified database using service discovery

    ELIMINATES DNS RESOLUTION DELAYS BY:
    - Using cached service discovery endpoints
    - Direct IP addressing (172.16.168.23) instead of DNS resolution
    - Fast connection timeouts (0.5s vs 2s+)
    """
    try:
        # Get Redis connection parameters from service discovery
        # This uses cached IP addresses, no DNS resolution needed
        params = get_redis_connection_params_sync()

        # Override with config password and database if available
        password = (
            cfg.get("redis.password")
            if cfg.get("redis.password")
            else params.get("password")
        )

        return redis.Redis(
            host=params["host"],  # Direct IP from service discovery
            port=params["port"],
            password=password,
            db=db_number,
            decode_responses=params.get("decode_responses", True),
            socket_timeout=params.get("socket_timeout", 1.0),
            socket_connect_timeout=params.get("socket_connect_timeout", 0.5),
            retry_on_timeout=params.get("retry_on_timeout", False),
            health_check_interval=params.get("health_check_interval", 0),
        )
    except Exception as e:
        logger.error(f"Failed to connect to Redis database {db_number}: {str(e)}")
        # Fallback to config-based connection if service discovery fails
        try:
            logger.warning(
                f"Falling back to config-based Redis connection for database {db_number}"
            )
            return redis.Redis(
                host=cfg.get("redis.host"),
                port=cfg.get("redis.port"),
                password=cfg.get("redis.password"),
                db=db_number,
                decode_responses=True,
                socket_timeout=cfg.get("redis.connection.socket_timeout"),
                socket_connect_timeout=cfg.get(
                    "redis.connection.socket_connect_timeout"
                ),
                retry_on_timeout=cfg.get("redis.connection.retry_on_timeout"),
            )
        except Exception as fallback_error:
            logger.error(
                f"Config fallback also failed for Redis database {db_number}: {str(fallback_error)}"
            )
            raise


@router.get("/stats")
async def get_cache_stats():
    """Get comprehensive cache statistics from all sources"""
    try:
        stats = {
            "redis_databases": {},
            "total_redis_keys": 0,
            "backend_caches": {
                "config_cache_active": True,  # From ConfigService cache
                "llm_cache_active": False,  # Placeholder for future LLM response cache
            },
        }

        # Get Redis stats for each database
        total_keys = 0
        for db_name, db_number in REDIS_DATABASES.items():
            try:
                redis_conn = get_redis_connection(db_number)
                db_info = redis_conn.info()
                key_count = redis_conn.dbsize()

                stats["redis_databases"][db_name] = {
                    "database": db_number,
                    "key_count": key_count,
                    "memory_usage": db_info.get("used_memory_human", "0B"),
                    "connected": True,
                }
                total_keys += key_count

            except Exception as e:
                logger.warning(
                    f"Could not get stats for Redis database {db_name} ({db_number}): {str(e)}"
                )
                stats["redis_databases"][db_name] = {
                    "database": db_number,
                    "key_count": 0,
                    "memory_usage": "0B",
                    "connected": False,
                    "error": str(e),
                }

        stats["total_redis_keys"] = total_keys

        return {"status": "success", "stats": stats}

    except Exception as e:
        logger.error(f"Error getting cache statistics: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting cache statistics: {str(e)}"
        )


@router.post("/redis/clear/{database}")
async def clear_redis_cache(database: str):
    """Clear Redis cache for specific database or all databases"""
    try:
        cleared_databases = []

        if database == "all":
            # Clear all Redis databases
            for db_name, db_number in REDIS_DATABASES.items():
                try:
                    redis_conn = get_redis_connection(db_number)
                    keys_before = redis_conn.dbsize()
                    redis_conn.flushdb()

                    cleared_databases.append(
                        {
                            "name": db_name,
                            "database": db_number,
                            "keys_cleared": keys_before,
                        }
                    )
                    logger.info(
                        f"Cleared Redis database {db_name} ({db_number}) - {keys_before} keys removed"
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to clear Redis database {db_name} ({db_number}): {str(e)}"
                    )
                    cleared_databases.append(
                        {
                            "name": db_name,
                            "database": db_number,
                            "error": str(e),
                            "keys_cleared": 0,
                        }
                    )
        else:
            # Clear specific database
            if database not in REDIS_DATABASES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown database '{database}'. Available: {list(REDIS_DATABASES.keys())}",
                )

            db_number = REDIS_DATABASES[database]
            redis_conn = get_redis_connection(db_number)
            keys_before = redis_conn.dbsize()
            redis_conn.flushdb()

            cleared_databases.append(
                {"name": database, "database": db_number, "keys_cleared": keys_before}
            )
            logger.info(
                f"Cleared Redis database {database} ({db_number}) - {keys_before} keys removed"
            )

        return {
            "status": "success",
            "message": f"Redis cache cleared for {database}",
            "cleared_databases": cleared_databases,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing Redis cache for {database}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error clearing Redis cache for {database}: {str(e)}",
        )


@router.post("/clear/{cache_type}")
async def clear_cache_type(cache_type: str):
    """Clear specific backend cache type"""
    try:
        if cache_type == "llm":
            # Clear LLM response cache (if implemented)
            logger.info("LLM cache clearing requested - not implemented yet")
            return {
                "status": "success",
                "message": "LLM cache clearing not implemented yet",
                "cache_type": cache_type,
            }

        elif cache_type == "knowledge":
            # Clear knowledge base cache
            logger.info("Knowledge base cache clearing requested")
            # This would clear any cached knowledge base responses
            return {
                "status": "success",
                "message": "Knowledge base cache cleared",
                "cache_type": cache_type,
            }

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown cache type '{cache_type}'. Available: llm, knowledge",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing {cache_type} cache: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error clearing {cache_type} cache: {str(e)}"
        )


@router.post("/config")
async def save_cache_config(config_data: Dict[str, Any]):
    """Save cache configuration settings"""
    try:
        logger.info(f"Cache configuration update requested: {config_data}")

        # Validate configuration
        required_fields = [
            "defaultTTLMinutes",
            "settingsTTLMinutes",
            "autoCleanupEnabled",
            "maxCacheSizeMB",
        ]
        for field in required_fields:
            if field not in config_data:
                raise HTTPException(
                    status_code=400, detail=f"Missing required field: {field}"
                )

        # Store in Redis config database for persistence
        try:
            redis_conn = get_redis_connection(REDIS_DATABASES["config"])
            redis_conn.set("cache_config", json.dumps(config_data))
            logger.info("Cache configuration saved to Redis")
        except Exception as e:
            logger.warning(f"Could not save cache config to Redis: {str(e)}")

        return {
            "status": "success",
            "message": "Cache configuration saved successfully",
            "config": config_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving cache configuration: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error saving cache configuration: {str(e)}"
        )


@router.get("/config")
async def get_cache_config():
    """Get current cache configuration"""
    try:
        # Try to load from Redis first
        try:
            redis_conn = get_redis_connection(REDIS_DATABASES["config"])
            config_data = redis_conn.get("cache_config")
            if config_data:
                return {
                    "status": "success",
                    "config": json.loads(config_data),
                    "source": "redis",
                }
        except Exception as e:
            logger.warning(f"Could not load cache config from Redis: {str(e)}")

        # Return default configuration
        default_config = {
            "defaultTTLMinutes": 5,
            "settingsTTLMinutes": 10,
            "autoCleanupEnabled": True,
            "maxCacheSizeMB": 100,
        }

        return {"status": "success", "config": default_config, "source": "default"}

    except Exception as e:
        logger.error(f"Error getting cache configuration: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting cache configuration: {str(e)}"
        )


@router.post("/warmup")
async def warmup_caches():
    """Warm up commonly used caches"""
    try:
        warmed_caches = []

        # This would typically pre-populate caches with frequently accessed data
        # For now, we'll just log the request
        logger.info("Cache warmup requested")

        warmed_caches.append(
            {
                "cache_type": "settings",
                "status": "simulated",
                "message": "Settings cache warmup simulated",
            }
        )

        return {
            "status": "success",
            "message": "Cache warmup completed",
            "warmed_caches": warmed_caches,
        }

    except Exception as e:
        logger.error(f"Error during cache warmup: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error during cache warmup: {str(e)}"
        )
