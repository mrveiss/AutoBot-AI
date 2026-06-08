# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backward Compatibility Wrappers - Drop-in replacements for legacy APIs
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

from .enums import MemoryCategory, TaskPriority, TaskStatus
from .manager import UnifiedMemoryManager
from .models import MemoryEntry, TaskExecutionRecord

logger = get_logger(__name__)


class EnhancedMemoryManager(UnifiedMemoryManager):
    """
    Backward compatibility wrapper for enhanced_memory_manager.py

    All existing code using EnhancedMemoryManager continues to work
    without any changes. This is a drop-in replacement.

    Used by 7 files:
    - src/voice_processing_system.py
    - src/context_aware_decision_system.py
    - src/markdown_reference_system.py
    - src/computer_vision_system.py
    - src/takeover_manager.py
    - src/modern_ai_integration.py
    - backend/api/enhanced_memory.py
    """

    def __init__(self, db_path: str = "data/enhanced_memory.db"):
        """Initialize with enhanced_memory_manager.py defaults"""
        super().__init__(db_path=db_path, enable_cache=True, enable_monitoring=False)
        logger.info("EnhancedMemoryManager compatibility wrapper initialized")

    def log_task_execution(self, record: TaskExecutionRecord) -> str:
        """
        Alias for log_task (backward compatibility)

        ⚠️ WARNING: This is a synchronous method. DO NOT call from async code.
        For async code, create UnifiedMemoryManager directly and use:
            await manager.log_task(record)
        """
        return self.log_task_sync(record)

    def _run_sync(self, coro):
        """
        Run async coroutine synchronously (Issue #742 - backward compat helper).

        #7469: this helper now delegates to ``autobot_shared.async_compat.run_or_schedule``
        which carries the same try-loop / threadpool defensive pattern,
        deduplicated across the codebase. Behavior is identical; one
        source of truth ensures all callers stay in sync if the pattern
        ever needs an update.
        """
        from autobot_shared.async_compat import run_or_schedule

        return run_or_schedule(coro)

    def create_task_record(
        self,
        task_name: str,
        description: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        agent_type: str | None = None,
        inputs: Dict | None = None,
        parent_task_id: str | None = None,
        metadata: Dict | None = None,
    ) -> str:
        """
        Create a new task with auto-generated task_id (Issue #742).

        Args:
            task_name: Name of the task
            description: Task description
            priority: Task priority (default: MEDIUM)
            agent_type: Type of agent executing task
            inputs: Task inputs dictionary
            parent_task_id: Parent task ID if this is a subtask
            metadata: Additional metadata

        Returns:
            Generated task_id

        ⚠️ WARNING: This is a synchronous method. DO NOT call from async code.
        """
        # Generate task_id using same pattern as enhanced_memory_manager.py
        task_id = hashlib.sha256(f"{task_name}_{datetime.now(tz=timezone.utc).isoformat()}".encode()).hexdigest()[:16]

        # Create TaskExecutionRecord
        record = TaskExecutionRecord(
            task_id=task_id,
            task_name=task_name,
            description=description,
            status=TaskStatus.PENDING,
            priority=priority,
            created_at=datetime.now(tz=timezone.utc),
            agent_type=agent_type,
            inputs=inputs,
            parent_task_id=parent_task_id,
            metadata=metadata,
        )

        # Log task synchronously
        self.log_task_sync(record)
        logger.info("Created task record: %s - %s", task_id, task_name)
        return task_id

    def start_task(self, task_id: str) -> bool:
        """
        Mark task as started (Issue #742).

        Args:
            task_id: Task identifier

        Returns:
            True if updated successfully, False otherwise

        ⚠️ WARNING: This is a synchronous method. DO NOT call from async code.
        """
        result = self._run_sync(
            self.update_task_status(
                task_id,
                TaskStatus.IN_PROGRESS,
                started_at=datetime.now(tz=timezone.utc),
            )
        )
        if result:
            logger.info("Started task: %s", task_id)
        else:
            logger.warning("Task not found for start: %s", task_id)
        return result

    def complete_task(
        self,
        task_id: str,
        outputs: Dict | None = None,
        status: TaskStatus = TaskStatus.COMPLETED,
    ) -> bool:
        """
        Mark task as completed (Issue #742).

        Args:
            task_id: Task identifier
            outputs: Optional task outputs
            status: Task status (default: COMPLETED)

        Returns:
            True if updated successfully, False otherwise

        ⚠️ WARNING: This is a synchronous method. DO NOT call from async code.
        """
        # Calculate duration by fetching task and computing from started_at
        task = self._run_sync(self.get_task(task_id))
        if not task:
            logger.warning("Task not found for completion: %s", task_id)
            return False

        completed_at = datetime.now(tz=timezone.utc)
        duration = None
        if task.started_at:
            duration = (completed_at - task.started_at).total_seconds()

        result = self._run_sync(
            self.update_task_status(
                task_id,
                status,
                completed_at=completed_at,
                duration_seconds=duration,
                outputs=outputs,
            )
        )

        if result:
            logger.info("Completed task: %s (duration: %ss)", task_id, duration)
        return result

    def fail_task(self, task_id: str, error_message: str, retry_count: int = 0) -> bool:
        """
        Mark task as failed (Issue #742).

        Args:
            task_id: Task identifier
            error_message: Error description
            retry_count: Number of retries attempted

        Returns:
            True if updated successfully, False otherwise

        ⚠️ WARNING: This is a synchronous method. DO NOT call from async code.
        """
        result = self._run_sync(
            self.update_task_status(
                task_id,
                TaskStatus.FAILED,
                completed_at=datetime.now(tz=timezone.utc),
                error_message=error_message,
                retry_count=retry_count,
            )
        )

        if result:
            logger.error("Failed task: %s - %s", task_id, error_message)
        else:
            logger.warning("Task not found for failure: %s", task_id)
        return result

    def get_task_history_sync(
        self,
        agent_type: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
        days_back: int = 30,
    ) -> List[TaskExecutionRecord]:
        """
        Query task history synchronously (Issue #742).

        Args:
            agent_type: Filter by agent type
            status: Filter by task status
            limit: Maximum results
            days_back: How many days back to search

        Returns:
            List of TaskExecutionRecord matching filters

        ⚠️ WARNING: This is a synchronous method. DO NOT call from async code.
        """
        # Convert days_back to start_date
        start_date = datetime.now(tz=timezone.utc) - timedelta(days=days_back)

        return self._run_sync(
            self.get_task_history(
                agent_type=agent_type,
                status=status,
                priority=None,
                start_date=start_date,
                end_date=None,
                limit=limit,
            )
        )

    def cleanup_old_data(self, days_to_keep: int = 90) -> Dict:
        """
        Cleanup old records (Issue #742).

        Args:
            days_to_keep: Retention period in days

        Returns:
            Dictionary with cleanup statistics (matches original API):
            - tasks_deleted: Number of old tasks/memories deleted
            - embeddings_deleted: Number of old embeddings deleted (0 in unified manager)

        ⚠️ WARNING: This is a synchronous method. DO NOT call from async code.
        """
        memories_deleted = self._run_sync(self.cleanup_old_memories(days_to_keep))

        # Match original enhanced_memory_manager.py return structure
        result = {
            "tasks_deleted": memories_deleted,
            "embeddings_deleted": 0,  # Unified manager doesn't track embeddings separately
        }
        logger.info("Cleanup completed: %s", result)
        return result


class LongTermMemoryManager:
    """Backward compatibility wrapper for memory_manager.py."""

    def __init__(self, config_path: str | None = None, db_path: str = "data/agent_memory.db"):
        """
        Initialize with memory_manager.py defaults

        Args:
            config_path: Legacy parameter (ignored, kept for backward compatibility)
            db_path: Path to SQLite database (default: "data/agent_memory.db")
        """
        self._unified = UnifiedMemoryManager(
            db_path=db_path,
            enable_cache=True,
            enable_monitoring=False,
            retention_days=90,
        )
        logger.info("LongTermMemoryManager compatibility wrapper initialized at %s", db_path)

    async def store_memory(
        self,
        category: str,
        content: str,
        metadata: Dict | None = None,
        embedding: bytes | None = None,
    ) -> int:
        """Map old API to new unified API"""
        # Convert string category to enum if possible
        try:
            cat = MemoryCategory[category.upper()]
        except (KeyError, AttributeError):
            cat = category  # Use as-is if not in enum

        return await self._unified.store_memory(cat, content, metadata, embedding=embedding)

    async def retrieve_memories(
        self, category: str, filters: Dict | None = None, limit: int = 100
    ) -> List[MemoryEntry]:
        """Map old API to new unified API"""
        filters = filters or {}

        try:
            cat = MemoryCategory[category.upper()]
        except (KeyError, AttributeError):
            cat = category

        return await self._unified.retrieve_memories(
            cat,
            limit=limit,
            start_date=filters.get("start_date"),
            end_date=filters.get("end_date"),
            reference_path=filters.get("reference_path"),
        )

    async def search_by_metadata(self, metadata_query: Dict) -> List[MemoryEntry]:
        """
        Search by metadata (limited implementation).

        WARNING: This is a limited implementation that converts metadata values
        to a text search query. It does NOT perform true metadata key/value matching.
        Results may include false positives if content happens to contain the
        metadata values as text.

        Args:
            metadata_query: Dictionary of metadata key/value pairs to search for

        Returns:
            List of MemoryEntry where content matches the search query
        """
        # Convert to content search (limited - does not do true metadata matching)
        query = " ".join(str(v) for v in metadata_query.values())
        return await self._unified.search_memories(query)

    async def initialize(self) -> None:
        """Initialize the underlying storage (called by orchestrator on startup)."""
        await self._unified._ensure_initialized()
        logger.info("LongTermMemoryManager initialized")

    async def cleanup(self) -> None:
        """Cleanup hook called by orchestrator on shutdown (no-op: no resources to release)."""
        logger.info("LongTermMemoryManager cleanup complete")

    async def search_relevant_context(self, query: str) -> List[MemoryEntry]:
        """Search memories for context relevant to the given query."""
        return await self._unified.search_memories(query)

    async def cleanup_old_memories(self, retention_days: int | None = None) -> int:
        """Cleanup old memories"""
        return await self._unified.cleanup_old_memories(retention_days)


# ============================================================================
# GLOBAL INSTANCES (for drop-in replacement)
# ============================================================================

get_enhanced_memory_manager = lazy_singleton(EnhancedMemoryManager)
get_long_term_memory_manager = lazy_singleton(LongTermMemoryManager)


__all__ = [
    "EnhancedMemoryManager",
    "LongTermMemoryManager",
    "get_enhanced_memory_manager",
    "get_long_term_memory_manager",
]
