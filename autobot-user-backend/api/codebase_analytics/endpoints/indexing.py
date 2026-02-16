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

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.constants.path_constants import PATH


class IndexCodebaseRequest(BaseModel):
    """Request model for indexing a codebase path."""

    root_path: Optional[str] = Field(
        default=None,
        description="Path to index. Defaults to PROJECT_ROOT if not provided.",
    )


from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

from ..scanner import (
    _active_tasks,
    _current_indexing_task_id,
    _tasks_lock,
    _tasks_sync_lock,
    do_indexing_with_progress,
    indexing_tasks,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _check_existing_task() -> Optional[JSONResponse]:
    """Check if indexing task is already running (Issue #398: extracted)."""
    if _current_indexing_task_id is not None:
        existing_task = _active_tasks.get(_current_indexing_task_id)
        if existing_task and not existing_task.done():
            logger.info("🔒 Indexing already in progress: %s", _current_indexing_task_id)
            return JSONResponse(
                {
                    "task_id": _current_indexing_task_id,
                    "status": "already_running",
                    "message": (
                        f"Indexing is already in progress. Poll "
                        f"/api/analytics/codebase/index/status/{_current_indexing_task_id} "
                        "for progress."
                    ),
                }
            )
    return None


def _validate_and_get_path(request: Optional[IndexCodebaseRequest]) -> str:
    """Validate request path and return resolved path (Issue #398: extracted)."""
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


def _create_cleanup_callback(task_id: str):
    """Create cleanup callback for task completion (Issue #398: extracted)."""

    def cleanup_task(t):
        global _current_indexing_task_id
        with _tasks_sync_lock:
            _active_tasks.pop(task_id, None)
            if _current_indexing_task_id == task_id:
                _current_indexing_task_id = None
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
    Start background indexing of a codebase path (Issue #398: refactored).

    Returns immediately with a task_id that can be used to poll progress.
    Only one indexing task can run at a time.
    """
    global _current_indexing_task_id

    logger.info("✅ ENTRY: index_codebase endpoint called!")

    async with _tasks_lock:
        # Check for existing task
        existing_response = _check_existing_task()
        if existing_response:
            return existing_response

        # Validate and get path
        root_path = _validate_and_get_path(request)
        logger.info("📁 Indexing path = %s", root_path)

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

        # Cancel the task
        try:
            existing_task.cancel()
            logger.info("🛑 Cancelled indexing task: %s", task_id)

            # Update task status
            if task_id in indexing_tasks:
                indexing_tasks[task_id]["status"] = "cancelled"
                indexing_tasks[task_id]["error"] = "Cancelled by user"
                indexing_tasks[task_id]["failed_at"] = datetime.now().isoformat()

            # Clear current task
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
