# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Codebase indexing endpoints
"""

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_path
from constants.path_constants import PATH


class IndexCodebaseRequest(BaseModel):
    """Request model for indexing a codebase path."""

    root_path: str | None = Field(
        default=None,
        description="Path to index. Defaults to PROJECT_ROOT if not provided.",
    )
    source_id: str | None = Field(
        default=None,
        description="Code source registry ID (#1133). Resolves to the source's clone_path.",
    )


from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

from ..scanner import (
    _active_tasks,
    _current_indexing_task_id,
    _index_queue,
    _load_task_from_redis,
    _persist_queue_entry,
    _pop_queue_entry_redis,
    _run_indexing_subprocess,
    _tasks_lock,
    _tasks_sync_lock,
    indexing_tasks,
)

logger = get_logger(__name__)

router = APIRouter()


async def _check_existing_task_and_queue(source_id: str | None, root_path_for_queue: str) -> JSONResponse | None:
    """If a job is running, enqueue the request and return a queued response.

    Returns None when no job is running (caller should start a new job).
    Issue #1133: queuing replaces the old "already_running" rejection.
    Issue #1717: persists queue entry to Redis for restart survival.
    """
    if _current_indexing_task_id is None:
        return None
    existing_task = _active_tasks.get(_current_indexing_task_id)
    if existing_task is None or existing_task.done():
        return None
    # A job is running — add to FIFO queue
    position = len(_index_queue) + 1
    entry = {
        "source_id": source_id,
        "root_path": root_path_for_queue,
        "queued_at": datetime.now(tz=timezone.utc).isoformat(),
        "requested_by": "api",
    }
    _index_queue.append(entry)
    await _persist_queue_entry(entry)
    logger.info("Indexing queued (position %d): %s", position, root_path_for_queue)
    return JSONResponse(
        {
            "task_id": None,
            "status": "queued",
            "position": position,
            "message": (
                f"Queued behind current job (position {position}). "
                "The job will start automatically when the running "
                "job finishes."
            ),
        }
    )


class _SyncNeeded:
    """Sentinel returned when a code source needs syncing before indexing."""

    def __init__(self, source):
        self.source = source


async def _validate_and_get_path(
    request: IndexCodebaseRequest | None,
) -> "str | _SyncNeeded":
    """Validate request and return the resolved index path (Issue #398 + #1133).

    Returns the path string when ready. Returns a ``_SyncNeeded`` sentinel when
    the source's clone directory does not exist and a sync must run first.
    """
    if request and request.source_id:
        from ..source_storage import get_source

        source = await get_source(request.source_id)
        if source is None:
            raise HTTPException(
                status_code=404,
                detail=f"Source {request.source_id} not found",
            )
        if not source.clone_path:
            from ..source_models import SourceStatus
            from .sources import _make_clone_path

            source.clone_path = _make_clone_path(source.id)
            source.status = SourceStatus.PENDING
            from ..source_storage import save_source as _save

            await _save(source)

        if not Path(source.clone_path).is_dir():
            return _SyncNeeded(source)

        return source.clone_path
    if request and request.root_path:
        try:
            safe_path_str = validate_path(request.root_path, must_exist=True)
            target_path = Path(safe_path_str)
        except (ValueError, PermissionError):
            raise HTTPException(
                status_code=400,
                detail="Invalid or inaccessible path",
            )
        try:
            if not target_path.is_dir():
                raise HTTPException(
                    status_code=400,
                    detail="Path is not a directory",
                )
        except OSError:
            raise HTTPException(
                status_code=400,
                detail="Cannot access path",
            )
        return str(target_path.resolve())
    return str(PATH.PROJECT_ROOT)


def _start_next_queued_job() -> None:
    """Dequeue and start the next pending indexing job (#1133, #1717)."""
    global _current_indexing_task_id
    if not _index_queue:
        return
    next_job = _index_queue.popleft()
    # Remove from Redis queue (#1717: keep in-memory and Redis in sync)
    asyncio.get_running_loop().create_task(_pop_queue_entry_redis())
    next_path = next_job.get("root_path", str(PATH.PROJECT_ROOT))
    next_source_id = next_job.get("source_id")
    next_task_id = str(uuid.uuid4())
    _current_indexing_task_id = next_task_id
    task = asyncio.get_running_loop().create_task(
        _run_indexing_subprocess(next_task_id, next_path, source_id=next_source_id)
    )
    _active_tasks[next_task_id] = task
    task.add_done_callback(_create_cleanup_callback(next_task_id))
    logger.info("Auto-started queued job %s for %s", next_task_id, next_path)


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


@router.post("/index")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="index_codebase",
    error_code_prefix="CODEBASE",
)
async def index_codebase(request: IndexCodebaseRequest | None = None):
    """
    Start background indexing of a codebase path (Issue #398: refactored, #1133: queued).

    Accepts optional source_id (code source registry) or root_path.
    Returns immediately with a task_id. If another job is running, queues the request.
    """
    global _current_indexing_task_id

    path_or_sync = await _validate_and_get_path(request)

    # Auto-sync: source clone directory missing → trigger sync
    if isinstance(path_or_sync, _SyncNeeded):
        source = path_or_sync.source
        from .sources import _do_sync

        asyncio.create_task(_do_sync(source))
        logger.info("Source %s needs sync before indexing", source.id)
        return JSONResponse(
            {
                "task_id": None,
                "status": "syncing",
                "message": (
                    "Source repository not yet cloned. "
                    "Sync started — indexing will begin "
                    "automatically after sync."
                ),
            }
        )

    root_path = path_or_sync
    source_id = request.source_id if request else None
    logger.info("Indexing path: %s", root_path)

    async with _tasks_lock:
        queued_response = await _check_existing_task_and_queue(source_id, root_path)
        if queued_response:
            return queued_response

        task_id = str(uuid.uuid4())
        _current_indexing_task_id = task_id
        task = asyncio.create_task(_run_indexing_subprocess(task_id, root_path, source_id=source_id))
        _active_tasks[task_id] = task

    task.add_done_callback(_create_cleanup_callback(task_id))
    logger.info("Indexing task %s started for %s", task_id, root_path)

    return JSONResponse(
        {
            "task_id": task_id,
            "status": "started",
            "message": (
                "Indexing started in background. Poll "
                "/api/analytics/codebase/index/status/"
                f"{task_id} for progress."
            ),
        }
    )


@router.get("/index/status/{task_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_indexing_status",
    error_code_prefix="CODEBASE",
)
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
    # #1179/#1210: Subprocess writes progress to Redis, not parent memory.
    # Prefer Redis (fresh) over in-memory (stale initial state).
    task_data = await _load_task_from_redis(task_id)
    if task_data is None:
        task_data = indexing_tasks.get(task_id)

    if task_data is None:
        return JSONResponse(
            status_code=404,
            content={
                "task_id": task_id,
                "status": "not_found",
                "error": "Task not found. It may have expired or never existed.",
            },
        )

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


@router.get("/index/current")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_indexing_job",
    error_code_prefix="CODEBASE",
)
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
            # Task finished — load final state from Redis (#1210)
            task_data = await _load_task_from_redis(current_task_id)
            if not task_data:
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

        # Task is still running — prefer Redis state (subprocess writes there)
        # because the subprocess has its own in-memory indexing_tasks (#1210).
        task_data = dict(indexing_tasks.get(current_task_id, {}))

    # Subprocess updates Redis, not parent's in-memory dict.
    # Load fresh state from Redis so progress actually advances (#1210).
    redis_state = await _load_task_from_redis(current_task_id)
    if redis_state:
        task_data = redis_state

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
            indexing_tasks[task_id]["failed_at"] = datetime.now(tz=timezone.utc).isoformat()

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
                "message": "Failed to cancel job",
            }
        )


@router.post("/index/cancel")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cancel_indexing_job",
    error_code_prefix="CODEBASE",
)
async def cancel_indexing_job():
    """
    Cancel the currently running indexing job

    Returns:
    - success: Whether the cancellation was successful
    - task_id: The cancelled job's task ID
    - message: Status message
    """
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
