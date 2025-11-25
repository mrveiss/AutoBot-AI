# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cache Management API
Provides endpoints for cache monitoring, warming, and management
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.utils.advanced_cache_manager import advanced_cache
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cache", tags=["cache_management"])


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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cache_stats",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_stats(data_type: Optional[str] = Query(None)):
    """Get cache statistics - global or for specific data type"""
    try:
        if data_type:
            stats = await advanced_cache.get_stats(data_type)
            return CacheStatsResponse(**stats)
        else:
            global_stats = await advanced_cache.get_stats()

            # Get individual data type stats
            data_type_stats = {}
            if "configured_data_types" in global_stats:
                for dt in global_stats["configured_data_types"]:
                    dt_stats = await advanced_cache.get_stats(dt)
                    data_type_stats[dt] = dt_stats

            global_stats["data_type_stats"] = data_type_stats
            return CacheStatsResponse(**global_stats)

    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error getting cache stats: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="warm_cache",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.post("/warm")
async def warm_cache(request: CacheWarmingRequest):
    """Warm up cache with commonly accessed data"""
    try:
        warmed_types = []
        failed_types = []

        for data_type in request.data_types:
            try:
                success = await _warm_data_type(data_type, request.force_refresh)
                if success:
                    warmed_types.append(data_type)
                else:
                    failed_types.append(data_type)
            except Exception as e:
                logger.error(f"Error warming cache for {data_type}: {e}")
                failed_types.append(data_type)

        return {
            "success": True,
            "warmed_types": warmed_types,
            "failed_types": failed_types,
            "total_warmed": len(warmed_types),
        }

    except Exception as e:
        logger.error(f"Error warming cache: {e}")
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
):
    """Invalidate cache entries"""
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
        logger.error(f"Error invalidating cache: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error invalidating cache: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_all_cache",
    error_code_prefix="CACHE_MANAGEMENT",
)
@router.post("/clear-all")
async def clear_all_cache():
    """Clear all cache data (use with caution)"""
    try:
        total_deleted = 0

        # Get all configured data types
        stats = await advanced_cache.get_stats()
        if "configured_data_types" in stats:
            for data_type in stats["configured_data_types"]:
                deleted = await advanced_cache.invalidate(data_type, "*")
                total_deleted += deleted

        return {
            "success": True,
            "message": "All cache data cleared",
            "total_deleted": total_deleted,
        }

    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")


async def _warm_data_type(data_type: str, force_refresh: bool = False) -> bool:
    """Warm cache for specific data type"""
    try:
        if data_type == "templates":
            # Warm workflow templates
            from src.workflow_templates import workflow_template_manager

            # Cache all templates list
            templates = workflow_template_manager.list_templates()
            template_data = []
            for template in templates:
                template_dict = {
                    "id": template.id,
                    "name": template.name,
                    "description": template.description,
                    "category": template.category.value,
                    "complexity": template.complexity.value,
                    "estimated_duration_minutes": template.estimated_duration_minutes,
                    "agents_involved": template.agents_involved,
                    "tags": template.tags,
                    "step_count": len(template.steps),
                    "approval_steps": sum(
                        1 for step in template.steps if step.requires_approval
                    ),
                    "variables": template.variables,
                }
                template_data.append(template_dict)

            # Cache templates list
            await advanced_cache.set(
                "templates",
                "list:all",
                {
                    "success": True,
                    "templates": template_data,
                    "total": len(template_data),
                },
            )

            # Cache individual template details
            for template in templates:
                template_detail = workflow_template_manager.get_template(template.id)
                if template_detail:
                    steps = []
                    for step in template_detail.steps:
                        steps.append(
                            {
                                "id": step.id,
                                "agent_type": step.agent_type,
                                "action": step.action,
                                "description": step.description,
                                "requires_approval": step.requires_approval,
                                "dependencies": step.dependencies,
                                "inputs": step.inputs,
                                "expected_duration_ms": step.expected_duration_ms,
                            }
                        )

                    await advanced_cache.set(
                        "templates",
                        f"detail:{template.id}",
                        {
                            "success": True,
                            "template": {
                                "id": template_detail.id,
                                "name": template_detail.name,
                                "description": template_detail.description,
                                "category": template_detail.category.value,
                                "complexity": template_detail.complexity.value,
                                "estimated_duration_minutes": (
                                    template_detail.estimated_duration_minutes
                                ),
                                "agents_involved": template_detail.agents_involved,
                                "tags": template_detail.tags,
                                "variables": template_detail.variables,
                                "steps": steps,
                            },
                        },
                    )

            logger.info(f"Warmed cache for {len(templates)} templates")
            return True

        elif data_type == "system_status":
            # Warm system status
            from backend.utils.connection_utils import ConnectionTester

            try:
                # Fast health status
                fast_status = await ConnectionTester.get_fast_health_status()
                await advanced_cache.set("health_checks", "health:fast", fast_status)

                # Detailed health status
                detailed_status = (
                    await ConnectionTester.get_comprehensive_health_status()
                )
                await advanced_cache.set(
                    "health_checks", "health:detailed", detailed_status
                )

                logger.info("Warmed cache for system health status")
                return True
            except Exception as e:
                logger.error(f"Error warming system status cache: {e}")
                return False

        elif data_type == "project_status":
            # Warm project status
            from src.project_state_manager import get_project_state_manager

            try:
                manager = get_project_state_manager()

                # Fast project status
                fast_status = manager.get_project_status(use_cache=True)
                await advanced_cache.set("project_status", "status:fast", fast_status)

                # Detailed project status
                detailed_status = manager.get_project_status(use_cache=False)
                await advanced_cache.set(
                    "project_status", "status:detailed", detailed_status
                )

                logger.info("Warmed cache for project status")
                return True
            except Exception as e:
                logger.error(f"Error warming project status cache: {e}")
                return False

        else:
            logger.warning(f"No warming strategy defined for data type: {data_type}")
            return False

    except Exception as e:
        logger.error(f"Error warming cache for {data_type}: {e}")
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
        logger.error(f"Error checking cache health: {e}")
        return {"status": "unhealthy", "error": str(e)}


# Startup cache warming function
async def warm_startup_cache():
    """Warm essential cache data during application startup"""
    try:
        logger.info("Starting cache warming during application startup")

        essential_data_types = ["templates", "system_status", "project_status"]
        warmed_count = 0

        for data_type in essential_data_types:
            try:
                success = await _warm_data_type(data_type)
                if success:
                    warmed_count += 1
                    logger.info(f"Successfully warmed cache for {data_type}")
                else:
                    logger.warning(f"Failed to warm cache for {data_type}")
            except Exception as e:
                logger.error(f"Error warming {data_type} during startup: {e}")

        logger.info(
            f"Startup cache warming completed: "
            f"{warmed_count}/{len(essential_data_types)} data types warmed"
        )
        return warmed_count

    except Exception as e:
        logger.error(f"Error during startup cache warming: {e}")
        return 0
