# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Redis-backed task status tracking for long-running background operations.

Enables polling of async task progress without in-memory state.
Used by documentation indexing, man pages, and other background tasks.
"""

import asyncio
import json
from dataclasses import asdict, dataclass

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)

# Redis key prefix for task status
TASK_STATUS_PREFIX = "task_status:"
TASK_TTL_SECONDS = 86400  # 24 hours


@dataclass
class TaskStatusRecord:
    """Task status information for background operations."""

    task_id: str
    status: str  # "queued", "running", "completed", "failed"
    message: str
    progress_percent: int = 0
    items_processed: int = 0
    items_total: int = 0
    error: str | None = None
    created_at: str = None
    updated_at: str = None
    elapsed_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = now_utc().isoformat()
        if self.updated_at is None:
            self.updated_at = now_utc().isoformat()


class TaskStatusManager:
    """Manages task status in Redis for persistent tracking."""

    @staticmethod
    def _get_redis_key(task_id: str) -> str:
        """Get Redis key for task status."""
        return f"{TASK_STATUS_PREFIX}{task_id}"

    @classmethod
    async def create_task(cls, task_id: str, message: str, total_items: int = 0) -> TaskStatusRecord:
        """
        Create a new task status in Redis.

        Args:
            task_id: Unique task identifier
            message: Initial status message
            total_items: Total items to process (for progress tracking)

        Returns:
            TaskStatusRecord object
        """
        status = TaskStatusRecord(
            task_id=task_id,
            status="queued",
            message=message,
            items_total=total_items,
            updated_at=now_utc().isoformat(),
        )

        await cls._save_to_redis(status)
        logger.info("[%s] Created task status: %s", task_id, message)
        return status

    @classmethod
    async def update_task(
        cls,
        task_id: str,
        status: str,
        message: str,
        progress_percent: int = None,
        items_processed: int = None,
        items_total: int = None,
        error: str = None,
        elapsed_seconds: float = None,
    ) -> TaskStatusRecord:
        """
        Update task status in Redis.

        Args:
            task_id: Task identifier
            status: Status ("running", "completed", "failed")
            message: Status message
            progress_percent: 0-100 progress
            items_processed: Items processed so far
            items_total: Total items
            error: Error message if failed
            elapsed_seconds: Elapsed time

        Returns:
            Updated TaskStatusRecord
        """
        existing = await cls.get_task(task_id)
        if not existing:
            # Create if doesn't exist
            existing = TaskStatusRecord(task_id=task_id, status="running", message="")

        # Update fields
        existing.status = status
        existing.message = message
        existing.updated_at = now_utc().isoformat()

        if progress_percent is not None:
            existing.progress_percent = progress_percent
        if items_processed is not None:
            existing.items_processed = items_processed
        if items_total is not None:
            existing.items_total = items_total
        if error is not None:
            existing.error = error
        if elapsed_seconds is not None:
            existing.elapsed_seconds = elapsed_seconds

        await cls._save_to_redis(existing)
        logger.debug("[%s] Updated status: %s (%s%%)", task_id, status, progress_percent)
        return existing

    @classmethod
    async def get_task(cls, task_id: str) -> TaskStatusRecord | None:
        """
        Retrieve task status from Redis.

        Returns:
            TaskStatusRecord or None if not found
        """
        try:
            redis_client = get_redis_client()
            data = await asyncio.to_thread(redis_client.get, cls._get_redis_key(task_id))

            if not data:
                return None

            task_dict = json.loads(data)
            return TaskStatusRecord(**task_dict)
        except Exception as e:
            logger.error("[%s] Error retrieving task status: %s", task_id, e)
            return None

    @classmethod
    async def _save_to_redis(cls, task_status: TaskStatusRecord) -> bool:
        """
        Save task status to Redis with TTL.

        Returns:
            True if successful
        """
        try:
            redis_client = get_redis_client()
            key = cls._get_redis_key(task_status.task_id)
            data = json.dumps(asdict(task_status))

            # Store with 24-hour expiration — use to_thread so the sync setex
            # call does not block the event loop (#4102).
            await asyncio.to_thread(redis_client.setex, key, TASK_TTL_SECONDS, data)
            return True
        except Exception as e:
            logger.error("[%s] Error saving to Redis: %s", task_status.task_id, e)
            return False

    @classmethod
    async def complete_task(
        cls,
        task_id: str,
        message: str,
        items_processed: int,
        elapsed_seconds: float,
    ) -> TaskStatusRecord:
        """
        Mark task as completed.

        Returns:
            Final TaskStatusRecord
        """
        return await cls.update_task(
            task_id=task_id,
            status="completed",
            message=message,
            progress_percent=100,
            items_processed=items_processed,
            elapsed_seconds=elapsed_seconds,
        )

    @classmethod
    async def fail_task(cls, task_id: str, error_message: str) -> TaskStatusRecord:
        """
        Mark task as failed.

        Returns:
            Final TaskStatusRecord with error
        """
        return await cls.update_task(
            task_id=task_id,
            status="failed",
            message="Task failed",
            progress_percent=0,
            error=error_message,
        )

    @classmethod
    async def delete_task(cls, task_id: str) -> bool:
        """
        Delete task status from Redis.

        Returns:
            True if deleted
        """
        try:
            redis_client = get_redis_client()
            await asyncio.to_thread(redis_client.delete, cls._get_redis_key(task_id))
            return True
        except Exception as e:
            logger.error("[%s] Error deleting task: %s", task_id, e)
            return False
