# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Claude Code Memory Import API (#16642).

Admin-gated endpoint that queues import of Claude Code auto-memory files
(see knowledge.claude_memory_importer) into the knowledge_facts store.

Kept as its own module rather than folded into api/knowledge_population.py:
that file and autobot_shared/ssot_config.py are both at their frozen
python-file-size-ratchet ceilings (#14236) and may not grow.

Endpoints:
- POST /import_claude_memory - Queue the import (background task)
- GET /import_claude_memory/status/{task_id} - Poll background job status
"""

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from knowledge.schemas.population import TaskQueuedResponse, TaskStatusResponse
from knowledge_factory import get_or_create_knowledge_base

logger = get_logger(__name__)

router = APIRouter(
    tags=["knowledge-population"],
    dependencies=[Depends(check_admin_permission)],
)


@router.post("/import_claude_memory", response_model=TaskQueuedResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="import_claude_memory",
    error_code_prefix="KNOWLEDGE_POPULATION",
)
async def import_claude_memory_endpoint(request: dict, req: Request):
    """
    Queue import of Claude Code auto-memory files into knowledge_facts (#16642).

    Body (optional): ``memory_dir`` — override the configured memory directory.
    Returns immediately with task_id. Use /import_claude_memory/status/{task_id} to poll.
    """
    from services.knowledge.task_status_manager import TaskStatusManager

    task_id = str(uuid.uuid4())
    memory_dir_override = (request or {}).get("memory_dir")

    await TaskStatusManager.create_task(
        task_id=task_id,
        message="Claude Code memory import started",
        total_items=0,
    )

    asyncio.create_task(_import_claude_memory_background(task_id, req.app, memory_dir_override))

    logger.info("Queued Claude Code memory import task: %s", task_id)

    return {
        "status": "queued",
        "task_id": task_id,
        "message": "Claude Code memory import started in background",
        "status_url": f"/api/knowledge_base/import_claude_memory/status/{task_id}",
    }


async def _import_claude_memory_background(task_id: str, app, memory_dir_override: str | None) -> None:
    """Background task: import Claude Code auto-memory files into knowledge_facts."""
    import time

    from knowledge.claude_memory_importer import get_claude_memory_dir, import_claude_memory
    from services.knowledge.task_status_manager import TaskStatusManager

    start_time = time.time()
    memory_dir = Path(memory_dir_override) if memory_dir_override else get_claude_memory_dir()

    try:
        await TaskStatusManager.update_task(
            task_id=task_id,
            status="running",
            message=f"Scanning {memory_dir}...",
            progress_percent=10,
        )

        kb_to_use = await get_or_create_knowledge_base(app, force_refresh=False)
        result = await import_claude_memory(kb_to_use, memory_dir)

        elapsed = time.time() - start_time
        await TaskStatusManager.complete_task(
            task_id=task_id,
            message=(
                f"Imported {result.created} created, {result.updated} updated, "
                f"{result.duplicate} duplicate, {result.failed} failed"
            ),
            items_processed=result.created + result.updated,
            elapsed_seconds=elapsed,
        )
        logger.info(
            "[%s] Claude Code memory import completed: %d created, %d updated, " "%d duplicate, %d failed (%.1fs)",
            task_id,
            result.created,
            result.updated,
            result.duplicate,
            result.failed,
            elapsed,
        )
    except Exception as e:
        logger.error("[%s] Claude Code memory import failed: %s", task_id, e)
        await TaskStatusManager.fail_task(task_id=task_id, error_message=str(e))


@router.get("/import_claude_memory/status/{task_id}", response_model=TaskStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_import_claude_memory_status",
    error_code_prefix="KNOWLEDGE_POPULATION",
)
async def get_import_claude_memory_status(task_id: str):
    """Poll the status of a background Claude Code memory import task (#16642)."""
    from services.knowledge.task_status_manager import TaskStatusManager

    task_status = await TaskStatusManager.get_task(task_id)

    if not task_status:
        return {
            "status": "not_found",
            "message": f"Task {task_id} not found",
            "task_id": task_id,
        }

    return {
        "task_id": task_status.task_id,
        "status": task_status.status,
        "message": task_status.message,
        "progress_percent": task_status.progress_percent,
        "items_processed": task_status.items_processed,
        "items_total": task_status.items_total,
        "error": task_status.error,
        "elapsed_seconds": task_status.elapsed_seconds,
        "created_at": task_status.created_at,
        "updated_at": task_status.updated_at,
    }
