# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cache management endpoints
"""

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

from ..storage import get_redis_connection
from .shared import _in_memory_storage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.delete("/cache")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_codebase_cache",
    error_code_prefix="CODEBASE",
)
async def clear_codebase_cache():
    """Clear codebase analysis cache from storage"""
    redis_client = await get_redis_connection()

    if redis_client:
        # Get all codebase keys
        # Issue #361 - avoid blocking
        def _collect_and_delete():
            keys_to_delete = []
            for key in redis_client.scan_iter(match="codebase:*"):
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
            for key in _in_memory_storage.scan_iter("codebase:*"):
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
