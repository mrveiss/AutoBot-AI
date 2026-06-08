# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Admin API for the document sync queue (#4453).

Exposes introspection endpoints over :class:`DocumentSyncQueue` so operators
can see what is pending, what failed, and how the worker is keeping up.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from api.schemas_knowledge import KnowledgeSyncQueuePruneResponse, KnowledgeSyncQueueResponse
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.knowledge.sync_queue import (
    SyncStatus,
    get_document_sync_queue,
    serialize_entry_for_api,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge-sync-queue"])


@router.get("/sync-queue", response_model=KnowledgeSyncQueueResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_sync_queue",
    error_code_prefix="KNOWLEDGE_SYNC_QUEUE",
)
async def get_sync_queue(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Return pending and failed entries plus summary counts.

    Pagination (``limit`` / ``offset``) is applied independently to each
    collection so the caller can page through long-tail failed entries
    without losing sight of the pending queue.
    """
    queue = get_document_sync_queue()
    pending = await queue.list_entries(SyncStatus.PENDING, limit=limit, offset=offset)
    failed = await queue.list_entries(SyncStatus.FAILED, limit=limit, offset=offset)
    counts = await queue.stats()
    return {
        "pending": [serialize_entry_for_api(e) for e in pending],
        "failed": [serialize_entry_for_api(e) for e in failed],
        "counts": counts,
        "limit": limit,
        "offset": offset,
    }


@router.post("/sync-queue/prune", response_model=KnowledgeSyncQueuePruneResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="prune_done_entries",
    error_code_prefix="KNOWLEDGE_SYNC_QUEUE",
)
async def prune_done_entries(
    older_than_seconds: int = Query(7 * 24 * 3600, ge=60),
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, int]:
    """Delete ``done`` entries older than ``older_than_seconds`` (default 7 days)."""
    queue = get_document_sync_queue()
    pruned = await queue.prune_done(older_than_seconds=older_than_seconds)
    return {"pruned": pruned}


__all__: List[str] = ["router"]
