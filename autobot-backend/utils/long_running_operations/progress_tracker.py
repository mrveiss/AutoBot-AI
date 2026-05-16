# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Progress Tracker for Long-Running Operations

Issue #381: Extracted from long_running_operations_framework.py god class refactoring.
Issue #6506 (Phase 2 of #6495): Refactored as a thin façade over
``TaskExecutionTracker``. Storage and Redis pub/sub broadcasting are delegated
to the canonical tracker; this façade retains only the in-process subscriber
callback model that the long-running-operations framework relies on
(``subscribe_to_progress`` provides synchronous callback semantics that Redis
pub/sub doesn't reproduce in-process).
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Dict

import redis.asyncio as redis

from autobot_shared.logging_manager import get_logger

from .types import LongRunningOperation, OperationProgress

logger = get_logger(__name__)


class OperationProgressTracker:
    """Façade over ``TaskExecutionTracker`` for in-flight operation progress.

    Public API is unchanged from the pre-#6506 implementation. Storage and
    Redis pub/sub broadcasting are delegated to ``TaskExecutionTracker``;
    in-process subscriber callbacks remain local to this façade.
    """

    def __init__(self, redis_client: redis.Redis | None = None):
        """Initialize façade. The ``redis_client`` argument is accepted for
        backward compatibility with existing callers but is not used directly —
        Redis access flows through ``TaskExecutionTracker``."""
        self.redis_client = redis_client
        self._subscribers: Dict[str, list] = {}

    async def subscribe_to_progress(self, operation_id: str, callback: Callable) -> None:
        """Subscribe an in-process callback for progress updates."""
        if operation_id not in self._subscribers:
            self._subscribers[operation_id] = []
        self._subscribers[operation_id].append(callback)

    async def unsubscribe_from_progress(self, operation_id: str, callback: Callable) -> None:
        """Unsubscribe an in-process callback."""
        if operation_id in self._subscribers:
            try:
                self._subscribers[operation_id].remove(callback)
            except ValueError:
                pass

    async def update_progress(
        self,
        operation: LongRunningOperation,
        current_step: str,
        progress_percent: float,
        items_processed: int = 0,
        total_items: int = 0,
        estimated_remaining: float = 0.0,
        details: Dict[str, Any] | None = None,
    ) -> None:
        """Update progress for an operation.

        Updates the in-memory ``operation.progress`` fields, fires in-process
        subscriber callbacks, then delegates persistent storage and Redis
        pub/sub broadcast to ``TaskExecutionTracker.update_progress``.
        """
        operation.progress.current_step = current_step
        operation.progress.progress_percent = progress_percent
        operation.progress.items_processed = items_processed
        operation.progress.total_items = total_items
        operation.progress.estimated_remaining = estimated_remaining
        operation.progress.last_update = datetime.now(tz=timezone.utc)

        if details:
            operation.progress.details.update(details)

        await self._notify_subscribers(operation)

        # Delegate storage + Redis broadcast to canonical tracker.
        # Import locally to avoid circular import at module load time.
        from task_execution_tracker import get_task_tracker

        tracker = get_task_tracker()
        await tracker.update_progress(
            task_id=operation.operation_id,
            progress_percent=progress_percent,
            current_step=current_step,
            items_processed=items_processed,
            total_items=total_items,
            estimated_remaining=estimated_remaining,
            details=dict(operation.progress.details),
            operation_type=operation.operation_type.value,
            name=operation.name,
            status=operation.status.value,
        )

    async def _notify_subscribers(self, operation: LongRunningOperation) -> None:
        """Notify in-process subscribers of a progress update."""
        operation_id = operation.operation_id
        if operation_id not in self._subscribers:
            return
        for callback in self._subscribers[operation_id]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(operation)
                else:
                    callback(operation)
            except Exception as e:
                logger.warning("Progress callback failed: %s", e)

    def get_cached_progress(self, operation_id: str) -> OperationProgress | None:
        """Return cached progress.

        With #6506 the in-memory cache is removed; use :meth:`get_progress`
        for the canonical (Redis-backed) snapshot. This synchronous method
        is retained for API compatibility and now always returns ``None``.
        """
        return None

    async def get_progress(self, operation_id: str) -> Dict[str, Any] | None:
        """Read the canonical progress snapshot from ``TaskExecutionTracker``."""
        from task_execution_tracker import get_task_tracker

        tracker = get_task_tracker()
        snapshot = await tracker.get_progress(operation_id)
        if snapshot is None:
            return None
        progress = snapshot.get("progress", {})
        return {
            "operation_id": operation_id,
            "current_step": progress.get("current_step", ""),
            "progress_percent": progress.get("progress_percent", 0.0),
            "items_processed": progress.get("items_processed", 0),
            "total_items": progress.get("total_items", 0),
            "estimated_remaining": progress.get("estimated_remaining", 0.0),
            "last_update": progress.get("last_update", ""),
            "details": progress.get("details", {}),
        }

    def clear_progress(self, operation_id: str) -> None:
        """Clear in-process subscribers for an operation."""
        self._subscribers.pop(operation_id, None)
