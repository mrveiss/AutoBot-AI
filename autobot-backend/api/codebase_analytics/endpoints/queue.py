# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analysis job queue management endpoints (#1133).

Exposes queue state and allows removal of queued jobs.
Mount point: /api/analytics/codebase (via router.py)
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

from ..scanner import (
    _active_tasks,
    _current_indexing_task_id,
    _index_queue,
    _tasks_lock,
    indexing_tasks,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_running_info(task_id: str) -> dict:
    """Build a dict describing the currently running job."""
    task_data = dict(indexing_tasks.get(task_id, {}))
    return {
        "task_id": task_id,
        "status": task_data.get("status", "running"),
        "started_at": task_data.get("started_at"),
        "source_id": task_data.get("source_id"),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_index_queue",
    error_code_prefix="CODEBASE",
)
@router.get("/index/queue")
async def get_index_queue():
    """Return the current indexing queue state.

    Response:
    - running: details of the running job, or null
    - queue:   list of queued jobs in FIFO order
    - queue_length: number of queued jobs
    """
    async with _tasks_lock:
        running = None
        if _current_indexing_task_id is not None:
            task = _active_tasks.get(_current_indexing_task_id)
            if task and not task.done():
                running = _build_running_info(_current_indexing_task_id)
        queue_snapshot = list(_index_queue)

    return JSONResponse(
        {
            "running": running,
            "queue": queue_snapshot,
            "queue_length": len(queue_snapshot),
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="dequeue_source",
    error_code_prefix="CODEBASE",
)
@router.delete("/index/queue/{source_id}")
async def dequeue_source(source_id: str):
    """Remove all pending queue entries for a given source_id."""
    async with _tasks_lock:
        before = len(_index_queue)
        to_keep = [item for item in _index_queue if item.get("source_id") != source_id]
        _index_queue.clear()
        _index_queue.extend(to_keep)
        removed = before - len(_index_queue)

    logger.info("Removed %d queue entries for source %s", removed, source_id)
    return JSONResponse(
        {
            "success": True,
            "source_id": source_id,
            "removed": removed,
            "remaining_queue_length": len(_index_queue),
        }
    )
