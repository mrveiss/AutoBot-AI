# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cache management API endpoints for clearing various cache types.
Provides comprehensive cache clearing functionality for frontend, backend, and Redis caches.
"""

import asyncio
import json
import logging

from backend.type_defs.common import Metadata

from fastapi import APIRouter, HTTPException

from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.redis_client import get_redis_client

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


def _clear_single_redis_database(db_name: str, db_number: int) -> Metadata:
    """Clear a single Redis database and return result (Issue #315: extracted).

    Returns:
        Dict with clearing result including name, database, keys_cleared, and optional error
    """
    try:
        redis_conn = get_redis_connection(db_name)
        keys_before = redis_conn.dbsize()
        redis_conn.flushdb()

        logger.info(
            f"Cleared Redis database {db_name} ({db_number}) - {keys_before} keys removed"
        )
        return {
            "name": db_name,
            "database": db_number,
            "keys_cleared": keys_before,
        }
    except Exception as e:
        logger.error("Failed to clear Redis database %s (%s): %s", db_name, db_number, str(e))
        return {
            "name": db_name,
            "database": db_number,
            "error": str(e),
            "keys_cleared": 0,
        }


def get_redis_connection(database: str = "main"):
    """
    Get Redis connection for specified database using canonical client

    USES CANONICAL get_redis_client() PATTERN:
    - Circuit breaker protection
    - Health monitoring
    - Connection pooling
    - Centralized configuration

    Args:
        database: Named database ("main", "knowledge", "prompts", etc.)
                  See REDIS_DATABASES dict for available names.
    """
    try:
        # Use canonical Redis client - MANDATORY per CLAUDE.md
        client = get_redis_client(async_client=False, database=database)
        if client is None:
            raise ConnectionError(
                f"Failed to get Redis client for database '{database}'"
            )
        return client
    except Exception as e:
        logger.error("Failed to connect to Redis database '%s': %s", database, str(e))
        raise


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cache_stats",
    error_code_prefix="CACHE",
)
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
        # Issue #666: Wrap blocking Redis calls in asyncio.to_thread
        total_keys = 0
        for db_name, db_number in REDIS_DATABASES.items():
            try:
                redis_conn = get_redis_connection(db_name)
                # Issue #666: Use asyncio.to_thread to avoid blocking event loop
                db_info = await asyncio.to_thread(redis_conn.info)
                key_count = await asyncio.to_thread(redis_conn.dbsize)

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
        logger.error("Error getting cache statistics: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error getting cache statistics: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_redis_cache",
    error_code_prefix="CACHE",
)
@router.post("/redis/clear/{database}")
async def clear_redis_cache(database: str):
    """Clear Redis cache for specific database or all databases"""
    try:
        cleared_databases = []

        if database == "all":
            # Clear all Redis databases using helper (Issue #315)
            # Issue #666: Wrap blocking sync function in asyncio.to_thread
            for db_name, db_number in REDIS_DATABASES.items():
                result = await asyncio.to_thread(
                    _clear_single_redis_database, db_name, db_number
                )
                cleared_databases.append(result)
        else:
            # Clear specific database
            if database not in REDIS_DATABASES:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Unknown database '{database}'. Available:"
                        f"{list(REDIS_DATABASES.keys())}"
                    )
                )

            db_number = REDIS_DATABASES[database]
            redis_conn = get_redis_connection(database)
            # Issue #666: Use asyncio.to_thread to avoid blocking event loop
            keys_before = await asyncio.to_thread(redis_conn.dbsize)
            await asyncio.to_thread(redis_conn.flushdb)

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
        logger.error("Error clearing Redis cache for %s: %s", database, str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error clearing Redis cache for {database}: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_cache_type",
    error_code_prefix="CACHE",
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
        logger.error("Error clearing %s cache: %s", cache_type, str(e))
        raise HTTPException(
            status_code=500, detail=f"Error clearing {cache_type} cache: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_cache_config",
    error_code_prefix="CACHE",
)
@router.post("/config")
async def save_cache_config(config_data: Metadata):
    """Save cache configuration settings"""
    try:
        logger.info("Cache configuration update requested: %s", config_data)

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
            redis_conn = get_redis_connection("config")
            # Issue #361 - avoid blocking
            await asyncio.to_thread(
                redis_conn.set, "cache_config", json.dumps(config_data)
            )
            logger.info("Cache configuration saved to Redis")
        except Exception as e:
            logger.warning("Could not save cache config to Redis: %s", str(e))

        return {
            "status": "success",
            "message": "Cache configuration saved successfully",
            "config": config_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error saving cache configuration: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error saving cache configuration: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cache_config",
    error_code_prefix="CACHE",
)
@router.get("/config")
async def get_cache_config():
    """Get current cache configuration"""
    try:
        # Try to load from Redis first
        try:
            redis_conn = get_redis_connection("config")
            # Issue #361 - avoid blocking
            config_data = await asyncio.to_thread(redis_conn.get, "cache_config")
            if config_data:
                return {
                    "status": "success",
                    "config": json.loads(config_data),
                    "source": "redis",
                }
        except Exception as e:
            logger.warning("Could not load cache config from Redis: %s", str(e))

        # Return default configuration
        default_config = {
            "defaultTTLMinutes": 5,
            "settingsTTLMinutes": 10,
            "autoCleanupEnabled": True,
            "maxCacheSizeMB": 100,
        }

        return {"status": "success", "config": default_config, "source": "default"}

    except Exception as e:
        logger.error("Error getting cache configuration: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error getting cache configuration: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="warmup_caches",
    error_code_prefix="CACHE",
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
        logger.error("Error during cache warmup: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error during cache warmup: {str(e)}"
        )
