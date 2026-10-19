# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cache coordinator endpoints, served under the ``/system`` mount (#743, #18722).

Moved out of ``api/system.py``, where the decorators hard-coded ``/api`` and so
were served at the doubled ``/api/system/api/cache/...``. ``api/system.py``
includes this router, so the paths below are relative to ``/api/system``.

``/cache/stats`` already belongs to the cache-manager stats in ``api/system.py``;
the coordinator's stats therefore live at ``/cache/coordinator/stats``.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.schemas_system import (
    SystemCacheClearResponse,
    SystemCacheCoordinatorStatsResponse,
    SystemCacheEvictResponse,
)
from auth_middleware import check_admin_permission
from autobot_shared.api_routing.deprecated_redirects import add_deprecated_redirects
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/cache/coordinator/stats", response_model=SystemCacheCoordinatorStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cache_coordinator_stats",
    error_code_prefix="SYSTEM",
)
async def get_cache_coordinator_stats(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get unified cache statistics from the cache coordinator.

    Returns stats for all registered caches including:
    - Individual cache metrics (size, hits, misses, hit_rate)
    - Total items across all caches
    - System memory percentage
    - Pressure trigger count

    Issue #744: Requires admin authentication.
    """
    try:
        from cache import get_cache_coordinator

        coordinator = await get_cache_coordinator()
        return coordinator.get_cache_stats()
    except Exception as e:
        logger.error("Error getting cache coordinator stats: %s", str(e))
        raise HTTPException(status_code=500, detail="Error getting cache coordinator stats")


@router.post("/cache/evict", response_model=SystemCacheEvictResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="trigger_cache_eviction",
    error_code_prefix="SYSTEM",
)
async def trigger_cache_eviction(admin_check: bool = Depends(check_admin_permission)):
    """
    Manually trigger coordinated cache eviction.

    Evicts items from all registered caches according to eviction_ratio.

    Issue #744: Requires admin authentication.
    """
    try:
        from cache import get_cache_coordinator

        coordinator = await get_cache_coordinator()
        evicted = await coordinator._coordinated_evict()

        return {
            "status": "eviction_complete",
            "evicted": evicted,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Error triggering cache eviction: %s", str(e))
        raise HTTPException(status_code=500, detail="Error triggering cache eviction")


@router.post("/cache/clear/{cache_name}", response_model=SystemCacheClearResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_cache",
    error_code_prefix="SYSTEM",
)
async def clear_cache(cache_name: str, admin_check: bool = Depends(check_admin_permission)):
    """
    Clear a specific cache by name.

    Args:
        cache_name: Name of the cache to clear (e.g., 'lru_memory', 'embedding')

    Issue #744: Requires admin authentication.
    """
    try:
        from cache import get_cache_coordinator

        coordinator = await get_cache_coordinator()
        if cache_name in coordinator._caches:
            await coordinator._caches[cache_name].clear()
            return {
                "status": "cleared",
                "cache": cache_name,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }

        raise HTTPException(status_code=404, detail=f"Cache '{cache_name}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error clearing cache %s: %s", cache_name, str(e))
        raise HTTPException(status_code=500, detail="Error clearing cache")


# #18722: the doubled paths answer 308 for one release; removal tracked in #18793.
add_deprecated_redirects(
    router,
    {
        ("GET", "/api/cache/stats"): "/cache/coordinator/stats",
        ("POST", "/api/cache/evict"): "/cache/evict",
        ("POST", "/api/cache/clear/{cache_name}"): "/cache/clear/{cache_name}",
    },
)
