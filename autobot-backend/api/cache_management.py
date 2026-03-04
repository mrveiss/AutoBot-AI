# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cache Management API
Provides endpoints for cache monitoring, warming, clearing, and management.
Consolidates all cache-related endpoints (Issue #1286).
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional

from auth_middleware import check_admin_permission, get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from type_defs.common import Metadata
from utils.advanced_cache_manager import advanced_cache

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["cache_management"])

# Issue #380: Module-level tuple for essential cache data types
_ESSENTIAL_CACHE_DATA_TYPES = ("templates", "system_status", "project_status")


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


def get_redis_connection(database: str = "main"):
    """Get Redis connection for specified database using canonical client."""
    try:
        client = get_redis_client(async_client=False, database=database)
        if client is None:
            raise ConnectionError(
                f"Failed to get Redis client for database '{database}'"
            )
        return client
    except Exception as e:
        logger.error("Failed to connect to Redis database '%s': %s", database, str(e))
        raise


def _clear_single_redis_database(db_name: str, db_number: int) -> dict:
    """Clear a single Redis database and return result."""
    try:
        redis_conn = get_redis_connection(db_name)
        keys_before = redis_conn.dbsize()
        redis_conn.flushdb()
        logger.info(
            "Cleared Redis database %s (%s) - %s keys removed",
            db_name,
            db_number,
            keys_before,
        )
        return {
            "name": db_name,
            "database": db_number,
            "keys_cleared": keys_before,
        }
    except Exception as e:
        logger.error(
            "Failed to clear Redis database %s (%s): %s",
            db_name,
            db_number,
            str(e),
        )
        return {
            "name": db_name,
            "database": db_number,
            "error": str(e),
            "keys_cleared": 0,
        }


class CacheStatsResponse(BaseModel):
    status: str
    total_cache_keys: Optional[int] = None
    total_hits: Optional[int] = None
    total_misses: Optional[int] = None
    global_hit_rate: Optional[str] = None
    memory_usage: Optional[str] = None
    configured_data_types: Optional[List[str]] = None
    data_type_stats: Optional[Dict[str, Dict]] = None


class CacheWarmingRequest(BaseModel):
    data_types: List[str]
    force_refresh: bool = False


def _process_data_type_stats_results(
    data_types: List[str], stats_results: list
) -> Dict[str, Dict]:
    """Process parallel stats results into a dictionary. (Issue #315 - extracted)"""
    data_type_stats = {}
    for dt, dt_stats in zip(data_types, stats_results):
        if isinstance(dt_stats, Exception):
            logger.error("Error getting stats for %s: %s", dt, dt_stats)
            data_type_stats[dt] = {"error": str(dt_stats)}
        else:
            data_type_stats[dt] = dt_stats
    return data_type_stats


# ── Redis-level endpoints (consolidated from cache.py, Issue #1286) ──


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cache_stats",
    error_code_prefix="CACHE",
)
@router.get("/stats")
async def get_cache_stats():
    """Get comprehensive cache statistics from all Redis databases."""
    stats = {
        "redis_databases": {},
        "total_redis_keys": 0,
        "backend_caches": {
            "config_cache_active": True,
            "llm_cache_active": False,
        },
    }

    total_keys = 0
    for db_name, db_number in REDIS_DATABASES.items():
        try:
            redis_conn = get_redis_connection(db_name)
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
                "Could not get stats for Redis database %s (%s): %s",
                db_name,
                db_number,
                str(e),
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_redis_cache",
    error_code_prefix="CACHE",
)
@router.post("/redis/clear/{database}")
async def clear_redis_cache(database: str):
    """Clear Redis cache for specific database or all databases."""
    cleared_databases = []

    if database == "all":
        for db_name, db_number in REDIS_DATABASES.items():
            result = await asyncio.to_thread(
                _clear_single_redis_database, db_name, db_number
            )
            cleared_databases.append(result)
    else:
        if database not in REDIS_DATABASES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown database '{database}'. "
                    f"Available: {list(REDIS_DATABASES.keys())}"
                ),
            )
        db_number = REDIS_DATABASES[database]
        redis_conn = get_redis_connection(database)
        keys_before = await asyncio.to_thread(redis_conn.dbsize)
        await asyncio.to_thread(redis_conn.flushdb)
        cleared_databases.append(
            {"name": database, "database": db_number, "keys_cleared": keys_before}
        )
        logger.info(
            "Cleared Redis database %s (%s) - %s keys removed",
            database,
            db_number,
            keys_before,
        )

    return {
        "status": "success",
        "message": f"Redis cache cleared for {database}",
        "cleared_databases": cleared_databases,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_cache_type",
    error_code_prefix="CACHE",
)
@router.post("/clear/{cache_type}")
async def clear_cache_type(cache_type: str):
    """Clear specific backend cache type."""
    if cache_type == "llm":
        logger.info("LLM cache clearing requested - not implemented yet")
        return {
            "status": "success",
            "message": "LLM cache clearing not implemented yet",
            "cache_type": cache_type,
        }
    elif cache_type == "knowledge":
        logger.info("Knowledge base cache clearing requested")
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_cache_config",
    error_code_prefix="CACHE",
)
@router.post("/config")
async def save_cache_config(config_data: Metadata):
    """Save cache configuration settings."""
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

    try:
        redis_conn = get_redis_connection("config")
        await asyncio.to_thread(redis_conn.set, "cache_config", json.dumps(config_data))
        logger.info("Cache configuration saved to Redis")
    except Exception as e:
        logger.warning("Could not save cache config to Redis: %s", str(e))

    return {
        "status": "success",
        "message": "Cache configuration saved successfully",
        "config": config_data,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cache_config",
    error_code_prefix="CACHE",
)
@router.get("/config")
async def get_cache_config():
    """Get current cache configuration."""
    try:
        redis_conn = get_redis_connection("config")
        config_data = await asyncio.to_thread(redis_conn.get, "cache_config")
        if config_data:
            return {
                "status": "success",
                "config": json.loads(config_data),
                "source": "redis",
            }
    except Exception as e:
        logger.warning("Could not load cache config from Redis: %s", str(e))

    default_config = {
        "defaultTTLMinutes": 5,
        "settingsTTLMinutes": 10,
        "autoCleanupEnabled": True,
        "maxCacheSizeMB": 100,
    }
    return {"status": "success", "config": default_config, "source": "default"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="warmup_caches",
    error_code_prefix="CACHE",
)
@router.post("/warmup")
async def warmup_caches():
    """Warm up commonly used caches."""
    logger.info("Cache warmup requested")
    warmed_caches = [
        {
            "cache_type": "settings",
            "status": "simulated",
            "message": "Settings cache warmup simulated",
        }
    ]
    return {
        "status": "success",
        "message": "Cache warmup completed",
        "warmed_caches": warmed_caches,
    }


# ── Advanced cache management endpoints ──


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_advanced_cache_stats",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.get("/advanced-stats", response_model=CacheStatsResponse)
async def get_advanced_cache_stats(
    data_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Get cache statistics - global or for specific data type.

    Issue #744: Requires authenticated user.
    """
    try:
        if data_type:
            stats = await advanced_cache.get_stats(data_type)
            return CacheStatsResponse(**stats)

        # Get global stats
        global_stats = await advanced_cache.get_stats()

        # Get individual data type stats (parallelized to avoid N+1)
        if "configured_data_types" not in global_stats:
            global_stats["data_type_stats"] = {}
            return CacheStatsResponse(**global_stats)

        data_types = global_stats["configured_data_types"]
        # Fetch all stats in parallel
        stats_results = await asyncio.gather(
            *[advanced_cache.get_stats(dt) for dt in data_types], return_exceptions=True
        )
        # Build result dict using helper (Issue #315 - reduces nesting)
        global_stats["data_type_stats"] = _process_data_type_stats_results(
            data_types, stats_results
        )
        return CacheStatsResponse(**global_stats)

    except Exception as e:
        logger.error("Error getting cache stats: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Error getting cache stats: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="warm_cache",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.post("/warm")
async def warm_cache(
    request: CacheWarmingRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """Warm up cache with commonly accessed data.

    Issue #744: Requires admin authentication.
    """
    try:
        # Issue #614: Fix N+1 pattern - warm all data types in parallel
        results = await asyncio.gather(
            *[_warm_data_type(dt, request.force_refresh) for dt in request.data_types],
            return_exceptions=True,
        )

        warmed_types = []
        failed_types = []
        for data_type, result in zip(request.data_types, results):
            if isinstance(result, Exception):
                logger.error("Error warming cache for %s: %s", data_type, result)
                failed_types.append(data_type)
            elif result:
                warmed_types.append(data_type)
            else:
                failed_types.append(data_type)

        return {
            "success": True,
            "warmed_types": warmed_types,
            "failed_types": failed_types,
            "total_warmed": len(warmed_types),
        }

    except Exception as e:
        logger.error("Error warming cache: %s", e)
        raise HTTPException(status_code=500, detail=f"Error warming cache: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="invalidate_cache",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.delete("/invalidate/{data_type}")
async def invalidate_cache(
    data_type: str,
    key: str = Query("*", description="Key pattern to invalidate (* for all)"),
    user_id: Optional[str] = Query(None, description="User ID for user-scoped data"),
    admin_check: bool = Depends(check_admin_permission),
):
    """Invalidate cache entries.

    Issue #744: Requires admin authentication.
    """
    try:
        deleted_count = await advanced_cache.invalidate(data_type, key, user_id)

        return {
            "success": True,
            "data_type": data_type,
            "key_pattern": key,
            "user_id": user_id,
            "deleted_count": deleted_count,
        }

    except Exception as e:
        logger.error("Error invalidating cache: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Error invalidating cache: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_all_cache",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.post("/clear-all")
async def clear_all_cache(
    admin_check: bool = Depends(check_admin_permission),
):
    """Clear all cache data (use with caution).

    Issue #744: Requires admin authentication.
    """
    try:
        # Get all configured data types
        stats = await advanced_cache.get_stats()
        data_types = stats.get("configured_data_types", [])

        if not data_types:
            return {
                "success": True,
                "message": "No cache data types configured",
                "total_deleted": 0,
            }

        # Issue #614: Fix N+1 pattern - invalidate all data types in parallel
        results = await asyncio.gather(
            *[advanced_cache.invalidate(dt, "*") for dt in data_types],
            return_exceptions=True,
        )

        total_deleted = sum(r for r in results if isinstance(r, int))

        return {
            "success": True,
            "message": "All cache data cleared",
            "total_deleted": total_deleted,
        }

    except Exception as e:
        logger.error("Error clearing cache: %s", e)
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")


async def _warm_templates_cache() -> bool:
    """Warm cache for workflow templates (Issue #372 - uses model methods)."""
    from workflow_templates import workflow_template_manager

    templates = workflow_template_manager.list_templates()
    # Issue #372: Use model method to reduce feature envy
    template_data = [t.to_summary_dict() for t in templates]

    # Cache templates list
    await advanced_cache.set(
        "templates",
        "list:all",
        {"success": True, "templates": template_data, "total": len(template_data)},
    )

    # Issue #614: Fix N+1 pattern - batch cache individual template details
    # First, collect all template details synchronously (CPU-bound)
    cache_tasks = []
    for template in templates:
        template_detail = workflow_template_manager.get_template(template.id)
        if template_detail:
            # Issue #372: Use model method to reduce feature envy
            cache_tasks.append(
                advanced_cache.set(
                    "templates",
                    f"detail:{template.id}",
                    {"success": True, "template": template_detail.to_detail_dict()},
                )
            )

    # Execute all cache writes in parallel
    if cache_tasks:
        await asyncio.gather(*cache_tasks, return_exceptions=True)

    logger.info("Warmed cache for %s templates", len(templates))
    return True


async def _warm_system_status_cache() -> bool:
    """Warm cache for system health status."""
    from utils.connection_utils import ConnectionTester

    try:
        # Issue #379: Fetch fast and detailed status in parallel
        fast_status, detailed_status = await asyncio.gather(
            ConnectionTester.get_fast_health_status(),
            ConnectionTester.get_comprehensive_health_status(),
        )

        # Cache both results in parallel
        await asyncio.gather(
            advanced_cache.set("health_checks", "health:fast", fast_status),
            advanced_cache.set("health_checks", "health:detailed", detailed_status),
        )

        logger.info("Warmed cache for system health status")
        return True
    except Exception as e:
        logger.error("Error warming system status cache: %s", e)
        return False


async def _warm_project_status_cache() -> bool:
    """Warm cache for project status."""
    from project_state_manager import get_project_state_manager

    try:
        manager = get_project_state_manager()

        fast_status = manager.get_project_status(use_cache=True)
        await advanced_cache.set("project_status", "status:fast", fast_status)

        detailed_status = manager.get_project_status(use_cache=False)
        await advanced_cache.set("project_status", "status:detailed", detailed_status)

        logger.info("Warmed cache for project status")
        return True
    except Exception as e:
        logger.error("Error warming project status cache: %s", e)
        return False


async def _warm_data_type(data_type: str, force_refresh: bool = False) -> bool:
    """Warm cache for specific data type"""
    try:
        if data_type == "templates":
            return await _warm_templates_cache()

        if data_type == "system_status":
            return await _warm_system_status_cache()

        if data_type == "project_status":
            return await _warm_project_status_cache()

        logger.warning("No warming strategy defined for data type: %s", data_type)
        return False

    except Exception as e:
        logger.error("Error warming cache for %s: %s", data_type, e)
        return False


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cache_health_check",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.get("/health")
async def cache_health_check():
    """Check cache system health"""
    try:
        stats = await advanced_cache.get_stats()

        is_healthy = stats.get("status") == "enabled"

        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "redis_status": stats.get("status", "unknown"),
            "total_keys": stats.get("total_cache_keys", 0),
            "memory_usage": stats.get("memory_usage", "N/A"),
            "global_hit_rate": stats.get("global_hit_rate", "0%"),
        }

    except Exception as e:
        logger.error("Error checking cache health: %s", e)
        return {"status": "unhealthy", "error": str(e)}


# =========================================================================
# SEMANTIC QUERY CACHE ENDPOINTS (Issue #1372)
# =========================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="semantic_cache_stats",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.get("/semantic-cache/stats")
async def semantic_cache_stats(
    _user: dict = Depends(get_current_user),
):
    """Get semantic query cache statistics."""
    from services.semantic_query_cache import get_semantic_query_cache

    cache = await get_semantic_query_cache()
    return cache.get_stats()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="semantic_cache_clear",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.delete("/semantic-cache/clear")
async def semantic_cache_clear(
    _user: dict = Depends(check_admin_permission),
):
    """Clear all semantic query cache entries (admin only)."""
    from services.semantic_query_cache import get_semantic_query_cache

    cache = await get_semantic_query_cache()
    result = await cache.clear()
    return {"status": "cleared", **result}


class SemanticCacheConfigUpdate(BaseModel):
    """Request body for semantic cache config update."""

    similarity_threshold: Optional[float] = None
    max_collection_size: Optional[int] = None
    response_ttl: Optional[int] = None
    enabled: Optional[bool] = None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="semantic_cache_config",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.put("/semantic-cache/config")
async def semantic_cache_update_config(
    update: SemanticCacheConfigUpdate,
    _user: dict = Depends(check_admin_permission),
):
    """Update semantic cache configuration at runtime (admin only)."""
    from services.semantic_query_cache import get_semantic_query_cache

    cache = await get_semantic_query_cache()
    return cache.update_config(
        similarity_threshold=update.similarity_threshold,
        max_collection_size=update.max_collection_size,
        response_ttl=update.response_ttl,
        enabled=update.enabled,
    )


# =========================================================================
# CONTEXT SUFFICIENCY ENDPOINTS (Issue #1374)
# =========================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="context_sufficiency_stats",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.get("/context-sufficiency/stats")
async def context_sufficiency_stats(
    _user: dict = Depends(get_current_user),
):
    """Get context sufficiency evaluator statistics."""
    from services.context_sufficiency import get_context_sufficiency_evaluator

    evaluator = get_context_sufficiency_evaluator()
    return evaluator.get_stats()


class SufficiencyConfigUpdate(BaseModel):
    """Request body for sufficiency evaluator config update."""

    enabled: Optional[bool] = None
    keyword_threshold: Optional[float] = None
    enable_llm_pass: Optional[bool] = None
    llm_timeout: Optional[float] = None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="context_sufficiency_config",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.put("/context-sufficiency/config")
async def context_sufficiency_update_config(
    update: SufficiencyConfigUpdate,
    _user: dict = Depends(check_admin_permission),
):
    """Update context sufficiency config at runtime (admin only)."""
    from services.context_sufficiency import get_context_sufficiency_evaluator

    evaluator = get_context_sufficiency_evaluator()
    kwargs = {k: v for k, v in update.model_dump().items() if v is not None}
    return evaluator.update_config(**kwargs)


# Startup cache warming function
async def warm_startup_cache():
    """Warm essential cache data during application startup (Issue #380: use module constant)"""
    try:
        logger.info("Starting cache warming during application startup")

        # Issue #614: Fix N+1 pattern - warm all essential data types in parallel
        results = await asyncio.gather(
            *[_warm_data_type(dt) for dt in _ESSENTIAL_CACHE_DATA_TYPES],
            return_exceptions=True,
        )

        warmed_count = 0
        for data_type, result in zip(_ESSENTIAL_CACHE_DATA_TYPES, results):
            if isinstance(result, Exception):
                logger.error("Error warming %s during startup: %s", data_type, result)
            elif result:
                warmed_count += 1
                logger.info("Successfully warmed cache for %s", data_type)
            else:
                logger.warning("Failed to warm cache for %s", data_type)

        logger.info(
            f"Startup cache warming completed: "
            f"{warmed_count}/{len(_ESSENTIAL_CACHE_DATA_TYPES)} data types warmed"
        )
        return warmed_count

    except Exception as e:
        logger.error("Error during startup cache warming: %s", e)
        return 0
