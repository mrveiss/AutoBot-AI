# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Memory Manager Protocols - Interface Segregation Principle
"""

from typing import Any, Dict, List, Protocol

from .enums import MemoryCategory
from .models import MemoryEntry, TaskExecutionRecord


class ITaskStorage(Protocol):
    """
    Interface for task-specific storage operations

    Implementing classes must provide task execution history tracking
    with full lifecycle management.
    """

    async def log_task(self, record: TaskExecutionRecord) -> str:
        """Log a new task execution record"""
        ...

    async def update_task(self, task_id: str, **updates) -> bool:
        """Update task fields"""
        ...

    async def get_task(self, task_id: str) -> TaskExecutionRecord | None:
        """Retrieve single task by ID"""
        ...

    async def get_task_history(self, filters: Dict[str, Any]) -> List[TaskExecutionRecord]:
        """Query task history with filters"""
        ...

    async def get_stats(self) -> Dict[str, Any]:
        """Get task storage statistics"""
        ...


class IGeneralStorage(Protocol):
    """
    Interface for general purpose storage operations

    Implementing classes must provide category-based storage
    with metadata search capabilities.

    #13688: reads are owner-scoped. Implementations must apply ``user_id`` as a
    query predicate rather than trusting callers to filter afterwards.
    """

    async def store(self, entry: MemoryEntry) -> int:
        """Store a memory entry (must carry a ``user_id``)"""
        ...

    async def retrieve(
        self, user_id: str, category: MemoryCategory | str, filters: Dict[str, Any]
    ) -> List[MemoryEntry]:
        """Retrieve one owner's memories by category and filters"""
        ...

    async def search(self, user_id: str, query: str) -> List[MemoryEntry]:
        """Search one owner's memories by content/metadata"""
        ...

    async def cleanup_old(self, retention_days: int) -> int:
        """Remove old entries beyond retention period"""
        ...

    async def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        ...


class ICacheManager(Protocol):
    """
    Interface for caching operations

    Implementing classes must provide LRU caching with statistics.
    """

    def get(self, key: str) -> Any | None:
        """Get item from cache"""
        ...

    def put(self, key: str, value: Any) -> None:
        """Put item in cache"""
        ...

    def evict(self, count: int) -> int:
        """Evict items from cache"""
        ...

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        ...


__all__ = [
    "ITaskStorage",
    "IGeneralStorage",
    "ICacheManager",
]
