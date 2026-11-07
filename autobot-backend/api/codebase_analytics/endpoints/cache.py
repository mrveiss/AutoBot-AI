# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Cache management endpoints
"""

import asyncio

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, bounded, with_error_handling
from autobot_shared.logging_manager import get_logger

from ..storage import get_redis_connection
from .shared import _in_memory_storage

logger = get_logger(__name__)

router = APIRouter()


@router.delete("/cache")
@bounded(60.0)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_codebase_cache",
    error_code_prefix="CODEBASE",
)
async def clear_codebase_cache(
    source_id: str = Query(..., min_length=1, description="Required (#17758): the source whose cache to clear"),
):
    """Clear ONE code source's analysis cache from storage.

    Issue #1772 scoped deletion to per-project keys when a source_id was
    supplied. #17758: it is now required, because the `else "codebase:*"` branch
    made a request that omitted the parameter delete **every** source's cached
    analytics -- reachable by leaving a query string off a DELETE.

    There is deliberately no "clear all sources" mode here. Destroying every
    project's cached analysis is not something a caller should express by
    omission, and adding it as an explicit flag would be adding a destructive
    capability this change has no mandate to invent.
    """
    redis_client = await get_redis_connection()
    match_pattern = f"codebase:{source_id}:*"

    if redis_client:
        # Get all codebase keys
        # Issue #361 - avoid blocking
        def _collect_and_delete():
            keys_to_delete = []
            for key in redis_client.scan_iter(match=match_pattern):
                keys_to_delete.append(key)
            if keys_to_delete:
                redis_client.delete(*keys_to_delete)
            return keys_to_delete

        keys_to_delete = await asyncio.to_thread(_collect_and_delete)
        storage_type = "redis"
    else:
        # Clear in-memory storage
        if _in_memory_storage:
            keys_to_delete = []
            for key in _in_memory_storage.scan_iter(match_pattern):
                keys_to_delete.append(key)

            _in_memory_storage.delete(*keys_to_delete)
            deleted_count = len(keys_to_delete)
        else:
            deleted_count = 0

        storage_type = "memory"

    return JSONResponse(
        {
            "status": "success",
            "message": (
                f"Cleared {len(keys_to_delete) if redis_client else deleted_count} "
                f"cache entries from {storage_type}"
            ),
            "deleted_keys": len(keys_to_delete) if redis_client else deleted_count,
            "storage_type": storage_type,
        }
    )
