# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Memory Manager - Main memory management class
"""

import asyncio
import gc
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .cache import LRUCacheManager
from .enums import MemoryCategory, StorageStrategy, TaskPriority, TaskStatus
from .models import MemoryEntry, TaskExecutionRecord
from .monitor import MemoryMonitor
from .protocols import ICacheManager, IGeneralStorage, ITaskStorage
from .storage import GeneralStorage, TaskStorage

logger = logging.getLogger(__name__)


class UnifiedMemoryManager:
    """
    Unified Memory Manager - Phase 5 Consolidation

    Combines features from 5 memory managers into a single, reusable,
    SOLID-principles-based implementation.

    Features:
    - Task execution history (from enhanced_memory_manager.py)
    - General purpose memory (from memory_manager.py)
    - LRU caching (from optimized_memory_manager.py)
    - Memory monitoring (from optimized_memory_manager.py)
    - Unified storage API with strategy pattern
    - Async-first design with sync wrappers
    - Backward compatibility wrappers

    Design Principles:
    1. Single Responsibility: Each component has ONE job
    2. Interface Segregation: Multiple protocols for different use cases
    3. Dependency Injection: Components injectable via constructor
    4. Strategy Pattern: Unified store() method with StorageStrategy enum
    5. Composition over Inheritance: Components composed, not inherited
    6. Async-First: All public methods async, sync wrappers provided
    7. DRY: Single implementation (no separate sync/async files)

    Example Usage:
        >>> # Task execution (enhanced_memory API)
        >>> manager = UnifiedMemoryManager()
        >>> record = TaskExecutionRecord(
        ...     task_id="task-001",
        ...     task_name="Process Document",
        ...     status=TaskStatus.PENDING,
        ...     priority=TaskPriority.HIGH,
        ...     created_at=datetime.now()
        ... )
        >>> await manager.log_task(record)

        >>> # General memory (memory_manager API)
        >>> await manager.store_memory(
        ...     MemoryCategory.FACT,
        ...     "AutoBot supports multi-modal AI",
        ...     metadata={"source": "documentation"}
        ... )

        >>> # Caching (optimized_memory API)
        >>> manager.cache_put("key", "value")
        >>> value = manager.cache_get("key")

        >>> # Unified API with strategy
        >>> await manager.store(record, StorageStrategy.TASK_EXECUTION)
        >>> await manager.store(entry, StorageStrategy.GENERAL_MEMORY)
    """

    def __init__(
        self,
        db_path: str = "data/unified_memory.db",
        enable_cache: bool = True,
        enable_monitoring: bool = False,
        cache_size: int = 1000,
        retention_days: int = 90,
        task_storage: Optional[ITaskStorage] = None,
        general_storage: Optional[IGeneralStorage] = None,
        cache_manager: Optional[ICacheManager] = None,
        monitor: Optional[MemoryMonitor] = None,
    ):
        """
        Initialize Unified Memory Manager

        Args:
            db_path: Path to SQLite database
            enable_cache: Enable LRU caching
            enable_monitoring: Enable memory monitoring (requires psutil)
            cache_size: Maximum cache size
            retention_days: Retention period for general memory
            task_storage: Custom task storage (dependency injection)
            general_storage: Custom general storage (dependency injection)
            cache_manager: Custom cache manager (dependency injection)
            monitor: Custom memory monitor (dependency injection)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days

        # Core components (dependency injection)
        self._task_storage = task_storage or TaskStorage(self.db_path)
        self._general_storage = general_storage or GeneralStorage(self.db_path)

        # Optional components
        self._cache = cache_manager or (
            LRUCacheManager(max_size=cache_size) if enable_cache else None
        )
        self._monitor = monitor or (MemoryMonitor() if enable_monitoring else None)

        # Database initialization flag and lock (thread-safe lazy initialization)
        self._initialized = False
        self._init_lock = asyncio.Lock()

        logger.info("Unified Memory Manager created at %s", self.db_path)

    async def _ensure_initialized(self):
        """
        Ensure database is initialized (thread-safe lazy initialization)

        Uses double-check locking to prevent race conditions when multiple
        concurrent calls attempt to initialize the database simultaneously.
        """
        if not self._initialized:
            async with self._init_lock:
                # Double-check after acquiring lock
                if not self._initialized:
                    await self._init_database()
                    self._initialized = True

    async def _init_database(self):
        """Initialize database schema"""
        # Issue #379: Initialize both storage backends in parallel
        await asyncio.gather(
            self._task_storage.initialize(),
            self._general_storage.initialize(),
        )

    # ========================================================================
    # TASK-SPECIFIC API (from enhanced_memory_manager.py)
    # ========================================================================

    async def log_task(self, record: TaskExecutionRecord) -> str:
        """
        Log task execution record (async)

        Args:
            record: TaskExecutionRecord to log

        Returns:
            task_id of logged record

        Raises:
            ValueError: If task_id or task_name is empty
        """
        # Input validation
        if not record.task_id or not record.task_id.strip():
            raise ValueError("task_id cannot be empty")
        if not record.task_name or not record.task_name.strip():
            raise ValueError("task_name cannot be empty")

        await self._ensure_initialized()
        return await self._task_storage.log_task(record)

    def log_task_sync(self, record: TaskExecutionRecord) -> str:
        """
        Log task execution record (sync wrapper)

        Backward compatibility wrapper for synchronous code.

        Handles both sync and async contexts properly by detecting if an event
        loop is already running and using a thread executor in that case.

        For async code, prefer using: await manager.log_task(record)
        """
        try:
            asyncio.get_running_loop()
            # Already in async context - use thread executor
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.log_task(record))
                return future.result()
        except RuntimeError:
            # No running loop - safe to use asyncio.run
            return asyncio.run(self.log_task(record))

    async def update_task_status(
        self, task_id: str, status: TaskStatus, **kwargs
    ) -> bool:
        """
        Update task status and optional fields

        Args:
            task_id: Task identifier
            status: New task status
            **kwargs: Additional fields to update
                - started_at: datetime
                - completed_at: datetime
                - duration_seconds: float
                - error_message: str
                - outputs: Dict
                - retry_count: int

        Returns:
            True if updated, False otherwise

        Raises:
            ValueError: If task_id is empty or invalid kwargs provided
        """
        # Input validation
        if not task_id or not task_id.strip():
            raise ValueError("task_id cannot be empty")
        if "duration_seconds" in kwargs and kwargs["duration_seconds"] < 0:
            raise ValueError("duration_seconds cannot be negative")
        if "retry_count" in kwargs and kwargs["retry_count"] < 0:
            raise ValueError("retry_count cannot be negative")

        await self._ensure_initialized()
        return await self._task_storage.update_task(task_id, status=status, **kwargs)

    async def get_task(self, task_id: str) -> Optional[TaskExecutionRecord]:
        """
        Retrieve single task by ID

        Args:
            task_id: Task identifier

        Returns:
            TaskExecutionRecord or None if not found
        """
        await self._ensure_initialized()
        return await self._task_storage.get_task(task_id)

    async def get_task_history(
        self,
        agent_type: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[TaskExecutionRecord]:
        """
        Query task execution history with filters

        Args:
            agent_type: Filter by agent type
            status: Filter by task status
            priority: Filter by task priority
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of results

        Returns:
            List of TaskExecutionRecord matching filters
        """
        await self._ensure_initialized()
        filters = {
            "agent_type": agent_type,
            "status": status,
            "priority": priority,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        }
        return await self._task_storage.get_task_history(filters)

    async def get_task_statistics(self) -> Dict[str, Any]:
        """
        Get task execution statistics

        Returns:
            Dictionary with task statistics:
            - total_tasks: Total number of tasks
            - by_status: Count by status
            - by_priority: Count by priority
        """
        await self._ensure_initialized()
        return await self._task_storage.get_stats()

    # ========================================================================
    # GENERAL PURPOSE API (from memory_manager.py)
    # ========================================================================

    async def store_memory(
        self,
        category: Union[MemoryCategory, str],
        content: str,
        metadata: Optional[Dict] = None,
        reference_path: Optional[str] = None,
        embedding: Optional[bytes] = None,
    ) -> int:
        """
        Store general purpose memory entry

        Args:
            category: Memory category (MemoryCategory enum or string)
            content: Memory content
            metadata: Optional metadata dictionary
            reference_path: Optional reference to markdown file
            embedding: Optional embedding vector (bytes)

        Returns:
            Entry ID

        Raises:
            ValueError: If category or content is empty/invalid
        """
        # Input validation
        if isinstance(category, str) and (not category or not category.strip()):
            raise ValueError("category cannot be empty string")
        if not content or not content.strip():
            raise ValueError("content cannot be empty")

        await self._ensure_initialized()
        entry = MemoryEntry(
            id=None,
            category=category,
            content=content,
            metadata=metadata or {},
            timestamp=datetime.now(),
            reference_path=reference_path,
            embedding=embedding,
        )
        return await self._general_storage.store(entry)

    async def retrieve_memories(
        self,
        category: Union[MemoryCategory, str],
        limit: int = 100,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        reference_path: Optional[str] = None,
    ) -> List[MemoryEntry]:
        """
        Retrieve memories by category and filters

        Args:
            category: Memory category
            limit: Maximum number of results
            start_date: Filter by start date
            end_date: Filter by end date
            reference_path: Filter by reference path

        Returns:
            List of MemoryEntry matching filters

        Raises:
            ValueError: If limit is invalid or date range is invalid
        """
        # Input validation
        if limit <= 0:
            raise ValueError("limit must be positive")
        if limit > 10000:
            raise ValueError("limit cannot exceed 10000")
        if start_date and end_date and start_date > end_date:
            raise ValueError("start_date cannot be after end_date")

        await self._ensure_initialized()
        filters = {
            "limit": limit,
            "start_date": start_date,
            "end_date": end_date,
            "reference_path": reference_path,
        }
        return await self._general_storage.retrieve(category, filters)

    async def search_memories(self, query: str) -> List[MemoryEntry]:
        """
        Search memories by content or metadata

        Args:
            query: Search query string

        Returns:
            List of MemoryEntry matching query
        """
        await self._ensure_initialized()
        return await self._general_storage.search(query)

    async def cleanup_old_memories(self, retention_days: Optional[int] = None) -> int:
        """
        Remove memories older than retention period

        Args:
            retention_days: Retention period (uses default if None)

        Returns:
            Number of entries deleted
        """
        await self._ensure_initialized()
        days = retention_days or self.retention_days
        return await self._general_storage.cleanup_old(days)

    # ========================================================================
    # CACHING API (from optimized_memory_manager.py)
    # ========================================================================

    def cache_get(self, key: str) -> Optional[Any]:
        """
        Get item from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        if not self._cache:
            return None
        return self._cache.get(key)

    def cache_put(self, key: str, value: Any) -> None:
        """
        Put item in cache

        Args:
            key: Cache key
            value: Value to cache
        """
        if self._cache:
            self._cache.put(key, value)

    def cache_evict(self, count: int) -> int:
        """
        Evict oldest items from cache

        Args:
            count: Number of items to evict

        Returns:
            Number of items evicted
        """
        if not self._cache:
            return 0
        return self._cache.evict(count)

    def cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache statistics:
            - enabled: Whether cache is enabled
            - size: Current cache size
            - max_size: Maximum cache size
            - hits: Cache hits
            - misses: Cache misses
            - hit_rate: Cache hit rate
        """
        if not self._cache:
            return {"enabled": False}
        return self._cache.stats()

    # ========================================================================
    # UNIFIED STORAGE API (Strategy Pattern)
    # ========================================================================

    async def _store_task_execution(self, data: Any) -> str:
        """Store data using task execution strategy. Issue #620.

        Args:
            data: Data to store (must be TaskExecutionRecord)

        Returns:
            Task ID of stored record

        Raises:
            TypeError: If data is not a TaskExecutionRecord
        """
        if not isinstance(data, TaskExecutionRecord):
            raise TypeError("TASK_EXECUTION strategy requires TaskExecutionRecord")
        return await self.log_task(data)

    async def _store_general_memory(self, data: Any) -> int:
        """Store data using general memory strategy. Issue #620.

        Args:
            data: Data to store (must be MemoryEntry)

        Returns:
            Entry ID of stored memory

        Raises:
            TypeError: If data is not a MemoryEntry
        """
        if not isinstance(data, MemoryEntry):
            raise TypeError("GENERAL_MEMORY strategy requires MemoryEntry")
        return await self.store_memory(
            data.category,
            data.content,
            data.metadata,
            data.reference_path,
            data.embedding,
        )

    def _store_cached(self, data: Any) -> str:
        """Store data using cache strategy. Issue #620.

        Args:
            data: Data to cache

        Returns:
            Cache key for stored data
        """
        key = hashlib.sha256(str(data).encode()).hexdigest()[:16]
        self.cache_put(key, data)
        return key

    async def store(
        self,
        data: Union[TaskExecutionRecord, MemoryEntry, Any],
        strategy: StorageStrategy = StorageStrategy.TASK_EXECUTION,
    ) -> Union[str, int]:
        """
        Unified storage interface with strategy pattern

        Args:
            data: Data to store (TaskExecutionRecord, MemoryEntry, or any)
            strategy: Storage strategy to use

        Returns:
            ID/key of stored data (type depends on strategy)

        Raises:
            TypeError: If data type doesn't match strategy
            ValueError: If strategy is unknown
        """
        await self._ensure_initialized()

        if strategy == StorageStrategy.TASK_EXECUTION:
            return await self._store_task_execution(data)
        elif strategy == StorageStrategy.GENERAL_MEMORY:
            return await self._store_general_memory(data)
        elif strategy == StorageStrategy.CACHED:
            return self._store_cached(data)
        else:
            raise ValueError(f"Unknown storage strategy: {strategy}")

    # ========================================================================
    # STATISTICS & MONITORING
    # ========================================================================

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive memory statistics

        Returns:
            Dictionary with statistics from all components:
            - task_storage: Task execution statistics
            - general_storage: General memory statistics
            - cache: Cache statistics
            - system_memory: System memory usage (if monitoring enabled)
        """
        await self._ensure_initialized()
        stats = {
            "task_storage": await self._task_storage.get_stats(),
            "general_storage": await self._general_storage.get_stats(),
            "cache": self.cache_stats(),
        }

        if self._monitor:
            stats["system_memory"] = self._monitor.get_usage()

        return stats

    def get_memory_usage(self) -> Optional[Dict[str, Any]]:
        """
        Get current system memory usage

        Returns:
            Memory usage dictionary or None if monitoring disabled
        """
        if not self._monitor:
            return None
        return self._monitor.get_usage()

    async def adaptive_cleanup(self, memory_threshold: float = 0.8) -> Dict[str, int]:
        """
        Perform adaptive cleanup based on memory pressure

        Args:
            memory_threshold: Memory usage threshold (0.0-1.0)

        Returns:
            Dictionary with cleanup counts:
            - cache_evicted: Items evicted from cache
            - memories_deleted: Old memories deleted
        """
        await self._ensure_initialized()
        cleanup_counts = {"cache_evicted": 0, "memories_deleted": 0}

        # Check if cleanup needed
        if self._monitor and self._monitor.should_cleanup(memory_threshold):
            logger.info("Memory pressure detected, performing adaptive cleanup")

            # Evict 20% of cache
            if self._cache:
                cache_size = self._cache.stats()["size"]
                evict_count = int(cache_size * 0.2)
                cleanup_counts["cache_evicted"] = self.cache_evict(evict_count)

            # Cleanup old memories
            cleanup_counts["memories_deleted"] = await self.cleanup_old_memories()

            # Force garbage collection
            gc.collect()

            logger.info("Cleanup completed: %s", cleanup_counts)

        return cleanup_counts


__all__ = ["UnifiedMemoryManager"]
