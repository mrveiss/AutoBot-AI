# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Helper for converting Celery AsyncResult to the legacy BackgroundTaskManager
response shape expected by the frontend (GH#6505).

Celery states:   PENDING → "pending"
                 STARTED → "running" (with meta progress/step if bound task)
                 PROGRESS (custom) → "running" with progress/step from meta
                 SUCCESS → "completed" with result
                 FAILURE → "failed" with error string
"""

from typing import Any, Dict

from celery.result import AsyncResult

# ---------------------------------------------------------------------------
# Helpers for latest-task-id tracking (replaces BackgroundTaskManager
# ``latest_result`` cache; stores only the Celery task ID in Redis)
# ---------------------------------------------------------------------------

_LATEST_TASK_KEY_TTL = 86400  # 24 h


async def store_latest_task_id(prefix: str, task_id: str) -> None:
    """Persist *task_id* under ``{prefix}latest_task_id`` in analytics Redis."""
    try:
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client(database="analytics")
        if redis:
            await redis.set(f"{prefix}latest_task_id", task_id, ex=_LATEST_TASK_KEY_TTL)
    except Exception:
        pass  # non-fatal; cached endpoint returns no_data


async def get_latest_task_result(prefix: str) -> Dict[str, Any] | None:
    """Return the latest completed task result for *prefix*, or *None*.

    Reads the stored Celery task_id and fetches its AsyncResult.
    Returns *None* when no completed result is available.
    """
    try:
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client(database="analytics")
        if not redis:
            return None
        raw = await redis.get(f"{prefix}latest_task_id")
        if not raw:
            return None
        task_id = raw.decode() if isinstance(raw, bytes) else raw
        result = AsyncResult(task_id)
        status = celery_result_to_status(result)
        if status and status["status"] == "completed" and status["result"]:
            return {"result": status["result"], "completed_at": status.get("completed_at")}
    except Exception:
        pass
    return None


def celery_result_to_status(result: AsyncResult) -> Dict[str, Any] | None:
    """Return a status dict compatible with the old BackgroundTaskManager API.

    Returns *None* only when the task ID is completely unknown to Celery
    (PENDING with no metadata — Celery returns PENDING for unknown IDs too).
    Callers should treat a bare PENDING as 404-or-pending depending on context.
    """
    state = result.state
    info = result.info or {}

    if state == "PENDING":
        return {
            "task_id": result.id,
            "status": "pending",
            "progress": 0.0,
            "current_step": None,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "result": None,
        }

    if state in ("STARTED", "PROGRESS"):
        meta = info if isinstance(info, dict) else {}
        return {
            "task_id": result.id,
            "status": "running",
            "progress": meta.get("progress", 0.0),
            "current_step": meta.get("step"),
            "started_at": meta.get("started_at"),
            "completed_at": None,
            "error": None,
            "result": None,
        }

    if state == "SUCCESS":
        payload = info if isinstance(info, dict) else {}
        return {
            "task_id": result.id,
            "status": "completed",
            "progress": 100.0,
            "current_step": "Complete",
            "started_at": payload.get("started_at"),
            "completed_at": payload.get("completed_at"),
            "error": None,
            "result": payload.get("result", info),
        }

    # FAILURE, REVOKED, or any other terminal state
    error_str = str(info) if not isinstance(info, dict) else info.get("error", str(info))
    return {
        "task_id": result.id,
        "status": "failed",
        "progress": 0.0,
        "current_step": None,
        "started_at": None,
        "completed_at": None,
        "error": error_str,
        "result": None,
    }
