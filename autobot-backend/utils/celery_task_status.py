# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Helper for converting Celery AsyncResult to the legacy BackgroundTaskManager
response shape expected by the frontend (GH#6505).

Celery states:   PENDING → "pending"
                 STARTED → "running" (with meta progress/step if bound task)
                 PROGRESS (custom) → "running" with progress/step from meta
                 SUCCESS → "completed" with result, unless the returned payload's own
                           ``status`` is ``"error"`` (a refusal), which maps to "failed" (#17982)
                 FAILURE → "failed" with error string
"""

from typing import Any, Dict

from celery.result import AsyncResult
from fastapi import HTTPException

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
        if status and status["status"] == "failed":
            # #17982: a failed scan is not "no data". Callers that read only
            # ``result`` see no result, as before; those that read ``error`` can
            # now tell the two apart.
            return {"error": status["error"], "completed_at": status.get("completed_at")}
    except Exception:
        pass
    return None


def _refusal_message(returned: Any) -> str | None:
    """The message of a task that RETURNED an error payload instead of raising, else None.

    Celery records a returned value as SUCCESS whatever it says, so a task that
    refuses (an unresolvable source, nothing to scan) used to surface as
    ``completed`` / ``progress 100`` / ``error None``: "scanned nothing" and
    "scanned and found nothing" were the same observable (#17982). The payload's
    own ``status`` is the discriminator every analytics task already writes.
    """
    if isinstance(returned, dict) and returned.get("status") == "error":
        return str(returned.get("message") or "the task reported an error without a message")
    return None


def _refused_status(task_id: str, payload: Dict[str, Any], message: str) -> Dict[str, Any]:
    """The status dict for a task that finished by refusing: failed, with its reason."""
    return {
        "task_id": task_id,
        "status": "failed",
        "progress": 0.0,
        "current_step": None,
        "started_at": payload.get("started_at"),
        "completed_at": payload.get("completed_at"),
        "error": message,
        "result": payload.get("result"),
    }


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
        refusal = _refusal_message(payload.get("result", info))
        if refusal is not None:
            return _refused_status(result.id, payload, refusal)
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


def known_task_status_or_404(task_id: str) -> Dict[str, Any]:
    """Status of a Celery task, or HTTP 404 when the ID is unknown or still bare-PENDING.

    Celery reports PENDING for IDs it has never seen, so for the polling
    endpoints that cannot tell "queued" from "never existed" a bare PENDING is
    treated as not found. One home for the five endpoints that carried this
    3-line check verbatim (#18557); endpoints that must return PENDING keep
    calling :func:`celery_result_to_status` directly.
    """
    status = celery_result_to_status(AsyncResult(task_id))
    if status is None or status["status"] == "pending":
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return status
