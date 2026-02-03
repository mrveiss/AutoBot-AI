# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Progress Tracker for Long-Running Operations

Issue #381: Extracted from long_running_operations_framework.py god class refactoring.
Handles real-time progress tracking and WebSocket broadcasting.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import redis.asyncio as redis

from .types import LongRunningOperation, OperationProgress

logger = logging.getLogger(__name__)


class OperationProgressTracker:
    """Tracks and broadcasts operation progress in real-time."""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize progress tracker with optional Redis client."""
        self.redis_client = redis_client
        self._progress_cache: Dict[str, OperationProgress] = {}
        self._subscribers: Dict[str, list] = {}

    async def subscribe_to_progress(
        self, operation_id: str, callback: Callable
    ) -> None:
        """Subscribe to progress updates for an operation."""
        if operation_id not in self._subscribers:
            self._subscribers[operation_id] = []
        self._subscribers[operation_id].append(callback)

    async def unsubscribe_from_progress(
        self, operation_id: str, callback: Callable
    ) -> None:
        """Unsubscribe from progress updates."""
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
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Update progress for an operation.

        Args:
            operation: The operation to update
            current_step: Current step description
            progress_percent: Progress percentage (0-100)
            items_processed: Number of items processed
            total_items: Total number of items
            estimated_remaining: Estimated seconds remaining
            details: Optional additional details
        """
        operation.progress.current_step = current_step
        operation.progress.progress_percent = progress_percent
        operation.progress.items_processed = items_processed
        operation.progress.total_items = total_items
        operation.progress.estimated_remaining = estimated_remaining
        operation.progress.last_update = datetime.now()

        if details:
            operation.progress.details.update(details)

        # Cache the progress
        self._progress_cache[operation.operation_id] = operation.progress

        # Broadcast to subscribers
        await self._notify_subscribers(operation)

        # Also broadcast via Redis pub/sub if available
        await self._broadcast_progress_update(operation)

    async def _notify_subscribers(
        self, operation: LongRunningOperation
    ) -> None:
        """Notify local subscribers of progress update."""
        operation_id = operation.operation_id
        if operation_id in self._subscribers:
            for callback in self._subscribers[operation_id]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(operation)
                    else:
                        callback(operation)
                except Exception as e:
                    logger.warning("Progress callback failed: %s", e)

    async def _broadcast_progress_update(
        self, operation: LongRunningOperation
    ) -> None:
        """Broadcast progress update via Redis pub/sub for WebSocket distribution."""
        if not self.redis_client:
            return

        try:
            progress_data = {
                "type": "operation_progress",
                "operation_id": operation.operation_id,
                "operation_type": operation.operation_type.value,
                "name": operation.name,
                "status": operation.status.value,
                "progress": {
                    "current_step": operation.progress.current_step,
                    "progress_percent": operation.progress.progress_percent,
                    "items_processed": operation.progress.items_processed,
                    "total_items": operation.progress.total_items,
                    "estimated_remaining": operation.progress.estimated_remaining,
                    "last_update": operation.progress.last_update.isoformat(),
                    "details": operation.progress.details,
                },
            }

            # Publish to operation-specific channel
            channel = f"operation:{operation.operation_id}:progress"
            await self.redis_client.publish(channel, json.dumps(progress_data))

            # Also publish to global operations channel
            await self.redis_client.publish(
                "operations:progress", json.dumps(progress_data)
            )

        except Exception as e:
            logger.warning("Failed to broadcast progress update: %s", e)

    def get_cached_progress(
        self, operation_id: str
    ) -> Optional[OperationProgress]:
        """Get cached progress for an operation."""
        return self._progress_cache.get(operation_id)

    async def get_progress(
        self, operation_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get current progress for an operation.

        Args:
            operation_id: The operation ID

        Returns:
            Progress dictionary or None
        """
        # Check cache first
        if operation_id in self._progress_cache:
            progress = self._progress_cache[operation_id]
            return {
                "operation_id": operation_id,
                "current_step": progress.current_step,
                "progress_percent": progress.progress_percent,
                "items_processed": progress.items_processed,
                "total_items": progress.total_items,
                "estimated_remaining": progress.estimated_remaining,
                "last_update": progress.last_update.isoformat(),
                "details": progress.details,
            }

        # Try Redis if available
        if self.redis_client:
            try:
                key = f"operation:{operation_id}:progress"
                data = await self.redis_client.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.warning("Failed to get progress from Redis: %s", e)

        return None

    def clear_progress(self, operation_id: str) -> None:
        """Clear cached progress for an operation."""
        self._progress_cache.pop(operation_id, None)
        self._subscribers.pop(operation_id, None)
