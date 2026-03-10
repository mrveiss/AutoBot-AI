# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared background task manager with Redis persistence (#1304).

Provides in-memory task tracking backed by Redis for cross-worker
visibility.  Handles orphan detection on worker restart and
stuck-task auto-recovery.

Usage::

    _manager = BackgroundTaskManager(redis_prefix="dep_task:")

    @router.post("/analyze")
    async def start(bg: BackgroundTasks):
        task_id = await _manager.create_task(params={...})
        bg.add_task(_run, task_id)
        return {"task_id": task_id, "status": "pending"}

    @router.get("/status/{task_id}")
    async def status(task_id: str):
        return await _manager.get_status(task_id)
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Defaults
_DEFAULT_TTL = 86400  # 24 hours
_DEFAULT_TIMEOUT = 600  # 10 minutes
_DEFAULT_MAX_CONCURRENT = 1


class BackgroundTaskManager:
    """Reusable background task manager with Redis persistence.

    Each instance tracks tasks under a unique ``redis_prefix``.
    """

    def __init__(
        self,
        redis_prefix: str,
        redis_ttl: int = _DEFAULT_TTL,
        task_timeout: int = _DEFAULT_TIMEOUT,
        max_concurrent: int = _DEFAULT_MAX_CONCURRENT,
    ):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._prefix = redis_prefix
        self._ttl = redis_ttl
        self._timeout = task_timeout
        self._max_concurrent = max_concurrent

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    async def _get_redis(self):
        """Return async Redis connection (analytics db)."""
        try:
            from autobot_shared.redis_client import get_redis_client

            return await get_redis_client(database="analytics", async_client=True)
        except Exception as exc:
            logger.debug("Redis unavailable (non-fatal): %s", exc)
            return None

    async def _save_to_redis(self, task_id: str) -> None:
        """Persist task state to Redis."""
        try:
            redis = await self._get_redis()
            if not redis:
                return
            state = self._tasks.get(task_id)
            if state:
                safe = {k: v for k, v in state.items() if k != "params"}
                await redis.set(
                    f"{self._prefix}{task_id}",
                    json.dumps(safe, default=str),
                    ex=self._ttl,
                )
        except Exception as exc:
            logger.debug("Task Redis save failed (non-fatal): %s", exc)

    async def _load_from_redis(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Load task from Redis (read-only).

        Returns the task state as-is.  With multiple uvicorn workers
        a task may be running in another worker's memory — marking it
        orphaned here would be a false positive.  Orphan cleanup is
        handled by ``_clear_orphaned`` (called from ``create_task``
        and ``clear_stuck``) which scans *all* keys.
        """
        try:
            redis = await self._get_redis()
            if not redis:
                return None
            data = await redis.get(f"{self._prefix}{task_id}")
            if not data:
                return None
            return json.loads(data)
        except Exception as exc:
            logger.debug("Task Redis load failed (non-fatal): %s", exc)
        return None

    async def _clear_orphaned(self) -> int:
        """Mark running-in-Redis-only tasks as failed."""
        cleared = 0
        try:
            redis = await self._get_redis()
            if not redis:
                return 0
            cursor = 0
            while True:
                cursor, keys = await redis.scan(
                    cursor,
                    match=f"{self._prefix}*",
                    count=100,
                )
                cleared += await self._mark_orphans(redis, keys)
                if cursor == 0:
                    break
        except Exception as exc:
            logger.debug("Orphan scan failed (non-fatal): %s", exc)
        return cleared

    async def _mark_orphans(self, redis, keys) -> int:
        """Mark individual orphaned keys as failed.

        Only marks tasks that are *not* in any worker's memory AND have
        exceeded the task timeout.  This avoids false positives in
        multi-worker deployments where one worker creates a task and
        another handles the cleanup call.
        """
        marked = 0
        now = datetime.now()
        for key in keys:
            data = await redis.get(key)
            if not data:
                continue
            task = json.loads(data)
            raw = key.decode() if isinstance(key, bytes) else key
            tid = raw.removeprefix(self._prefix)
            if task.get("status") != "running" or tid in self._tasks:
                continue
            # Only mark as orphaned if it has exceeded the timeout
            started = task.get("started_at")
            if started:
                try:
                    elapsed = (now - datetime.fromisoformat(started)).total_seconds()
                    if elapsed < self._timeout:
                        continue  # Still within timeout — may be running on another worker
                except (ValueError, TypeError):
                    pass
            task["status"] = "failed"
            task["error"] = "Task orphaned by backend restart"
            task["reason"] = "orphaned"
            task["completed_at"] = now.isoformat()
            await redis.set(
                f"{self._prefix}{tid}",
                json.dumps(task, default=str),
                ex=self._ttl,
            )
            marked += 1
            logger.info(
                "Cleared orphaned task %s%s",
                self._prefix,
                tid,
            )
        return marked

    # ------------------------------------------------------------------
    # Stuck-task cleanup
    # ------------------------------------------------------------------

    def _cleanup_stuck(self) -> int:
        """Mark timed-out in-memory tasks as failed."""
        cleaned = 0
        now = datetime.now()
        for tid, task in list(self._tasks.items()):
            if task.get("status") != "running":
                continue
            started = task.get("started_at")
            stuck = True
            if started:
                try:
                    elapsed = (now - datetime.fromisoformat(started)).total_seconds()
                    stuck = elapsed > self._timeout
                except (ValueError, TypeError):
                    pass
            if stuck:
                task["status"] = "failed"
                task["error"] = "Task timed out (auto-recovered)"
                task["reason"] = "timeout"
                task["completed_at"] = now.isoformat()
                cleaned += 1
                logger.warning("Auto-recovered stuck task %s", tid)
        return cleaned

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_task(self, params: Optional[dict] = None) -> str:
        """Create a new task; return its id.

        Raises ``HTTPException(409)`` when *max_concurrent*
        already running.  Clears orphaned/stuck tasks first.
        """
        await self._clear_orphaned()

        async with self._lock:
            self._cleanup_stuck()
            running = sum(
                1
                for t in self._tasks.values()
                if t.get("status") in ("pending", "running")
            )
            if running >= self._max_concurrent:
                raise HTTPException(
                    status_code=409,
                    detail="Analysis already running",
                )

            task_id = uuid.uuid4().hex[:8]
            self._tasks[task_id] = {
                "task_id": task_id,
                "status": "pending",
                "progress": 0.0,
                "current_step": None,
                "started_at": None,
                "completed_at": None,
                "error": None,
                "reason": None,
                "result": None,
                "params": params,
            }
            await self._save_to_redis(task_id)
        return task_id

    async def update_progress(self, task_id: str, step: str, progress: float) -> None:
        """Set current step and progress percentage."""
        task = self._tasks.get(task_id)
        if not task:
            return
        if task["status"] == "pending":
            task["status"] = "running"
            task["started_at"] = datetime.now().isoformat()
        task["current_step"] = step
        task["progress"] = min(progress, 100.0)
        await self._save_to_redis(task_id)

    async def complete_task(self, task_id: str, result: Any) -> None:
        """Mark task as completed with *result*.

        Also stores the result at ``{prefix}latest_result`` for quick
        retrieval on page load without triggering new analysis (#1540).
        """
        task = self._tasks.get(task_id)
        if not task:
            return
        task["status"] = "completed"
        task["progress"] = 100.0
        task["current_step"] = "Complete"
        task["completed_at"] = datetime.now().isoformat()
        task["result"] = result
        await self._save_to_redis(task_id)
        await self._save_latest_result(result, task["completed_at"])

    async def _save_latest_result(self, result: Any, completed_at: str) -> None:
        """Store latest completed result at a well-known Redis key (#1540)."""
        try:
            redis = await self._get_redis()
            if not redis:
                return
            payload = json.dumps(
                {
                    "result": result,
                    "completed_at": completed_at,
                },
                default=str,
            )
            await redis.set(
                f"{self._prefix}latest_result",
                payload,
                ex=self._ttl,
            )
        except Exception as exc:
            logger.debug("Latest result save failed (non-fatal): %s", exc)

    async def get_latest_result(self) -> Optional[Dict[str, Any]]:
        """Return the most recent completed result, or *None* (#1540).

        Reads from the ``{prefix}latest_result`` Redis key written by
        ``complete_task``.  Returns ``{"result": ..., "completed_at": ...}``
        or *None* if no cached result exists.
        """
        try:
            redis = await self._get_redis()
            if not redis:
                return None
            data = await redis.get(f"{self._prefix}latest_result")
            if not data:
                return None
            return json.loads(data)
        except Exception as exc:
            logger.debug("Latest result load failed (non-fatal): %s", exc)
        return None

    async def fail_task(
        self,
        task_id: str,
        error: str,
        reason: Optional[str] = None,
    ) -> None:
        """Mark task as failed with *error* message."""
        task = self._tasks.get(task_id)
        if not task:
            return
        task["status"] = "failed"
        task["error"] = error
        task["reason"] = reason
        task["completed_at"] = datetime.now().isoformat()
        await self._save_to_redis(task_id)

    async def get_status(self, task_id: str) -> Optional[dict]:
        """Return status dict (memory-first, Redis fallback).

        When loading from Redis, auto-detects zombie tasks (running
        longer than ``_timeout``) and marks them as failed so the
        frontend sees an error instead of infinite progress.
        """
        task = self._tasks.get(task_id)
        if task:
            return {k: v for k, v in task.items() if k != "params"}
        redis_task = await self._load_from_redis(task_id)
        if redis_task and redis_task.get("status") == "running":
            started = redis_task.get("started_at")
            if started:
                try:
                    elapsed = (
                        datetime.now() - datetime.fromisoformat(started)
                    ).total_seconds()
                    if elapsed > self._timeout:
                        redis_task["status"] = "failed"
                        redis_task["error"] = "Task timed out (auto-recovered)"
                        redis_task["reason"] = "timeout"
                        redis_task["completed_at"] = datetime.now().isoformat()
                        # Persist the cleanup to Redis
                        redis = await self._get_redis()
                        if redis:
                            try:
                                await redis.set(
                                    f"{self._prefix}{task_id}",
                                    json.dumps(redis_task, default=str),
                                    ex=self._ttl,
                                )
                            except Exception:
                                pass
                        logger.info(
                            "Auto-recovered zombie task %s "
                            "(running %.0fs, timeout %ds)",
                            task_id,
                            elapsed,
                            self._timeout,
                        )
                except (ValueError, TypeError):
                    pass
        return redis_task

    async def list_tasks(self) -> dict:
        """Return summary of all tracked tasks."""
        tasks = [
            {
                "task_id": tid,
                "status": t.get("status"),
                "progress": t.get("progress", 0),
                "current_step": t.get("current_step"),
            }
            for tid, t in self._tasks.items()
        ]
        return {"tasks": tasks, "count": len(tasks)}

    async def clear_stuck(self, force: bool = False) -> int:
        """Clean stuck tasks; if *force*, also clear Redis."""
        async with self._lock:
            cleaned = self._cleanup_stuck()
        if force:
            cleaned += await self._clear_orphaned()
        return cleaned

    async def delete_task(self, task_id: str) -> bool:
        """Remove a single task from memory and Redis."""
        async with self._lock:
            if task_id not in self._tasks:
                return False
            del self._tasks[task_id]
        redis = await self._get_redis()
        if redis:
            try:
                await redis.delete(f"{self._prefix}{task_id}")
            except Exception:
                pass
        return True

    async def clear_all(self) -> int:
        """Remove all tasks from memory and Redis."""
        count = len(self._tasks)
        redis = await self._get_redis()
        if redis:
            for tid in list(self._tasks):
                try:
                    await redis.delete(f"{self._prefix}{tid}")
                except Exception:
                    pass
        self._tasks.clear()
        return count
