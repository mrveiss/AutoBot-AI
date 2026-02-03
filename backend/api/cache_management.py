# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cache Management API
Provides endpoints for cache monitoring, warming, and management
"""

import asyncio
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.auth_middleware import check_admin_permission, get_current_user
from src.utils.advanced_cache_manager import advanced_cache
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cache", tags=["cache_management"])

# Issue #380: Module-level tuple for essential cache data types
_ESSENTIAL_CACHE_DATA_TYPES = ("templates", "system_status", "project_status")


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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cache_stats",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_stats(
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

        import asyncio
        data_types = global_stats["configured_data_types"]
        # Fetch all stats in parallel
        stats_results = await asyncio.gather(
            *[advanced_cache.get_stats(dt) for dt in data_types],
            return_exceptions=True
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

        total_deleted = sum(
            r for r in results if isinstance(r, int)
        )

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
    from src.workflow_templates import workflow_template_manager

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
    from backend.utils.connection_utils import ConnectionTester

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
    from src.project_state_manager import get_project_state_manager

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
