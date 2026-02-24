# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Codebase indexing endpoints
"""

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.constants.path_constants import PATH
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class IndexCodebaseRequest(BaseModel):
    """Request model for indexing a codebase path."""

    root_path: Optional[str] = Field(
        default=None,
        description="Path to index. Defaults to PROJECT_ROOT if not provided.",
    )
    source_id: Optional[str] = Field(
        default=None,
        description="Code source registry ID (#1133). Resolves to the source's clone_path.",
    )


from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

from ..scanner import (
    _active_tasks,
    _current_indexing_task_id,
    _index_queue,
    _tasks_lock,
    _tasks_sync_lock,
    do_indexing_with_progress,
    indexing_tasks,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _check_existing_task_and_queue(
    source_id: Optional[str], root_path_for_queue: str
) -> Optional[JSONResponse]:
    """If a job is running, enqueue the request and return a queued response.

    Returns None when no job is running (caller should start a new job).
    Issue #1133: queuing replaces the old "already_running" rejection.
    """
    if _current_indexing_task_id is None:
        return None
    existing_task = _active_tasks.get(_current_indexing_task_id)
    if existing_task is None or existing_task.done():
        return None
    # A job is running — add to FIFO queue
    from datetime import datetime as _dt

    position = len(_index_queue) + 1
    _index_queue.append(
        {
            "source_id": source_id,
            "root_path": root_path_for_queue,
            "queued_at": _dt.now().isoformat(),
            "requested_by": "api",
        }
    )
    logger.info("📋 Indexing queued (position %d): %s", position, root_path_for_queue)
    return JSONResponse(
        {
            "task_id": None,
            "status": "queued",
            "position": position,
            "message": (
                f"Queued behind current job (position {position}). "
                "The job will start automatically when the running job finishes."
            ),
        }
    )


async def _validate_and_get_path(request: Optional[IndexCodebaseRequest]) -> str:
    """Validate request and return the resolved index path (Issue #398 + #1133)."""
    if request and request.source_id:
        from ..source_storage import get_source

        source = await get_source(request.source_id)
        if source is None:
            raise HTTPException(
                status_code=404,
                detail=f"Source {request.source_id} not found",
            )
        if not source.clone_path:
            raise HTTPException(
                status_code=400,
                detail="Source has no clone path; sync it first",
            )
        return source.clone_path
    if request and request.root_path:
        target_path = Path(request.root_path)
        if not target_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Path does not exist: {request.root_path}",
            )
        if not target_path.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"Path is not a directory: {request.root_path}",
            )
        return str(target_path.resolve())
    return str(PATH.PROJECT_ROOT)


def _start_next_queued_job() -> None:
    """Dequeue and start the next pending indexing job if any (#1133)."""
    global _current_indexing_task_id
    if not _index_queue:
        return
    next_job = _index_queue.popleft()
    next_path = next_job.get("root_path", str(PATH.PROJECT_ROOT))
    next_task_id = str(uuid.uuid4())
    _current_indexing_task_id = next_task_id
    task = asyncio.get_event_loop().create_task(
        do_indexing_with_progress(next_task_id, next_path)
    )
    _active_tasks[next_task_id] = task
    task.add_done_callback(_create_cleanup_callback(next_task_id))
    logger.info("▶️  Auto-started queued job %s for %s", next_task_id, next_path)


def _create_cleanup_callback(task_id: str):
    """Create cleanup callback for task completion (Issue #398 + #1133: auto-dequeue)."""

    def cleanup_task(t):
        global _current_indexing_task_id
        with _tasks_sync_lock:
            _active_tasks.pop(task_id, None)
            if _current_indexing_task_id == task_id:
                _current_indexing_task_id = None
            _start_next_queued_job()
        logger.info("🧹 Task %s cleaned up", task_id)

    return cleanup_task


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="index_codebase",
    error_code_prefix="CODEBASE",
)
@router.post("/index")
async def index_codebase(request: Optional[IndexCodebaseRequest] = None):
    """
    Start background indexing of a codebase path (Issue #398: refactored, #1133: queued).

    Accepts optional source_id (code source registry) or root_path.
    Returns immediately with a task_id. If another job is running, queues the request.
    """
    global _current_indexing_task_id

    logger.info("✅ ENTRY: index_codebase endpoint called!")

    # Resolve the path first (may be async for source_id lookup)
    root_path = await _validate_and_get_path(request)
    source_id = request.source_id if request else None
    logger.info("📁 Indexing path = %s", root_path)

    async with _tasks_lock:
        # Check for existing task — queue if busy (#1133)
        queued_response = _check_existing_task_and_queue(source_id, root_path)
        if queued_response:
            return queued_response

        # Generate unique task ID and start task
        task_id = str(uuid.uuid4())
        logger.info("🆔 Generated task_id = %s", task_id)

        _current_indexing_task_id = task_id

        logger.info("🔄 About to create_task")
        task = asyncio.create_task(do_indexing_with_progress(task_id, root_path))
        logger.info("✅ Task created: %s", task)
        _active_tasks[task_id] = task
        logger.info("💾 Task stored in _active_tasks")

    # Add cleanup callback
    task.add_done_callback(_create_cleanup_callback(task_id))
    logger.info("🧹 Cleanup callback added")

    logger.info("📤 About to return JSONResponse")
    return JSONResponse(
        {
            "task_id": task_id,
            "status": "started",
            "message": (
                "Indexing started in background. Poll "
                "/api/analytics/codebase/index/status/{task_id} for progress."
            ),
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_indexing_status",
    error_code_prefix="CODEBASE",
)
@router.get("/index/status/{task_id}")
async def get_indexing_status(task_id: str):
    """
    Get the status of a background indexing task

    Returns:
    - task_id: The unique task identifier
    - status: "running" | "completed" | "failed" | "not_found"
    - progress: {current, total, percent, current_file, operation} (if running)
    - result: Final indexing results (if completed)
    - error: Error message (if failed)
    """
    if task_id not in indexing_tasks:
        return JSONResponse(
            status_code=404,
            content={
                "task_id": task_id,
                "status": "not_found",
                "error": "Task not found. It may have expired or never existed.",
            },
        )

    task_data = indexing_tasks[task_id]

    response = {
        "task_id": task_id,
        "status": task_data["status"],
        "progress": task_data.get("progress"),
        "result": task_data.get("result"),
        "error": task_data.get("error"),
        "started_at": task_data.get("started_at"),
        "completed_at": task_data.get("completed_at"),
        "failed_at": task_data.get("failed_at"),
    }

    return JSONResponse(response)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_indexing_job",
    error_code_prefix="CODEBASE",
)
@router.get("/index/current")
async def get_current_indexing_job():
    """
    Get the status of the currently running indexing job (if any)

    Returns:
    - has_active_job: Whether an indexing job is currently running
    - task_id: The current job's task ID (if running)
    - status: Current job status
    - progress: Current progress details
    """
    # All accesses to shared state under lock
    async with _tasks_lock:
        if _current_indexing_task_id is None:
            return JSONResponse(
                {
                    "has_active_job": False,
                    "task_id": None,
                    "status": "idle",
                    "message": "No indexing job is currently running",
                }
            )

        current_task_id = _current_indexing_task_id

        # Check if task is still running
        existing_task = _active_tasks.get(current_task_id)
        if existing_task is None or existing_task.done():
            # Task finished or was cleaned up
            task_data = dict(indexing_tasks.get(current_task_id, {}))
            return JSONResponse(
                {
                    "has_active_job": False,
                    "task_id": current_task_id,
                    "status": task_data.get("status", "unknown"),
                    "result": task_data.get("result"),
                    "error": task_data.get("error"),
                    "message": "Last indexing job has completed",
                }
            )

        # Task is still running - get a copy of task data
        task_data = dict(indexing_tasks.get(current_task_id, {}))

    return JSONResponse(
        {
            "has_active_job": True,
            "task_id": current_task_id,
            "status": task_data.get("status", "running"),
            "progress": task_data.get("progress"),
            "phases": task_data.get("phases"),
            "batches": task_data.get("batches"),
            "stats": task_data.get("stats"),
            "started_at": task_data.get("started_at"),
            "message": "Indexing job is in progress",
        }
    )


def _cancel_active_task(task_id: str, existing_task) -> JSONResponse:
    """Helper for cancel_indexing_job. Ref: #1088."""
    global _current_indexing_task_id
    try:
        existing_task.cancel()
        logger.info("\U0001f6d1 Cancelled indexing task: %s", task_id)

        if task_id in indexing_tasks:
            indexing_tasks[task_id]["status"] = "cancelled"
            indexing_tasks[task_id]["error"] = "Cancelled by user"
            indexing_tasks[task_id]["failed_at"] = datetime.now().isoformat()

        _current_indexing_task_id = None
        _active_tasks.pop(task_id, None)

        return JSONResponse(
            {
                "success": True,
                "task_id": task_id,
                "message": "Indexing job cancelled successfully",
            }
        )
    except Exception as e:
        logger.error("Failed to cancel task %s: %s", task_id, e)
        return JSONResponse(
            {
                "success": False,
                "task_id": task_id,
                "message": f"Failed to cancel job: {str(e)}",
            }
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cancel_indexing_job",
    error_code_prefix="CODEBASE",
)
@router.post("/index/cancel")
async def cancel_indexing_job():
    """
    Cancel the currently running indexing job

    Returns:
    - success: Whether the cancellation was successful
    - task_id: The cancelled job's task ID
    - message: Status message
    """
    global _current_indexing_task_id

    # All accesses to shared state under lock
    async with _tasks_lock:
        if _current_indexing_task_id is None:
            return JSONResponse(
                {
                    "success": False,
                    "task_id": None,
                    "message": "No indexing job is currently running",
                }
            )

        task_id = _current_indexing_task_id
        existing_task = _active_tasks.get(task_id)

        if existing_task is None or existing_task.done():
            return JSONResponse(
                {
                    "success": False,
                    "task_id": task_id,
                    "message": "Indexing job has already completed or was not found",
                }
            )

        return _cancel_active_task(task_id, existing_task)
