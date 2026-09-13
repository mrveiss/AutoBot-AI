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

import uuid

from fastapi import APIRouter, Depends, Request

from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.async_compat import fire_and_forget
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
async def import_claude_memory_endpoint(req: Request):
    """
    Queue import of Claude Code auto-memory files into knowledge_facts (#16642).

    Always imports from the configured memory directory (#16642 security
    review: no caller-supplied path — nothing to confine or validate).
    Returns immediately with task_id. Use /import_claude_memory/status/{task_id} to poll.
    """
    from services.knowledge.task_status_manager import TaskStatusManager

    task_id = str(uuid.uuid4())
    caller = await get_current_user(req)
    owner_id = str(caller.get("user_id") or caller.get("sub") or caller.get("username") or "")

    await TaskStatusManager.create_task(
        task_id=task_id,
        message="Claude Code memory import started",
        total_items=0,
    )

    fire_and_forget(
        _import_claude_memory_background(task_id, req.app, owner_id),
        name=f"import_claude_memory:{task_id}",
    )

    logger.info("Queued Claude Code memory import task: %s", task_id)

    return {
        "status": "queued",
        "task_id": task_id,
        "message": "Claude Code memory import started in background",
        "status_url": f"/api/knowledge_base/import_claude_memory/status/{task_id}",
    }


async def _import_claude_memory_background(task_id: str, app, owner_id: str) -> None:
    """Background task: import Claude Code auto-memory files into knowledge_facts."""
    import time

    from knowledge.claude_memory_importer import get_claude_memory_dir, import_claude_memory
    from services.knowledge.task_status_manager import TaskStatusManager

    start_time = time.time()
    memory_dir = get_claude_memory_dir()

    try:
        await TaskStatusManager.update_task(
            task_id=task_id,
            status="running",
            message=f"Scanning {memory_dir}...",
            progress_percent=10,
        )

        kb_to_use = await get_or_create_knowledge_base(app, force_refresh=False)
        result = await import_claude_memory(kb_to_use, memory_dir, owner_id)

        elapsed = time.time() - start_time
        await TaskStatusManager.complete_task(
            task_id=task_id,
            message=(
                f"Imported {result.created} created, {result.updated} updated, "
                f"{result.duplicate} duplicate, {result.blocked} blocked, {result.failed} failed"
            ),
            items_processed=result.created + result.updated,
            elapsed_seconds=elapsed,
        )
        logger.info(
            "[%s] Claude Code memory import completed: %d created, %d updated, "
            "%d duplicate, %d blocked, %d failed (%.1fs)",
            task_id,
            result.created,
            result.updated,
            result.duplicate,
            result.blocked,
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

    return task_status.to_response_dict()
