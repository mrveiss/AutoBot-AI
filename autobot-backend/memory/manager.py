# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Memory Manager - Canonical memory management class (Issue #10666 B2 consolidation)

Consolidates two previously separate managers:
- MemoryManager (memory/manager.py) — SQLite/LRU/task/general/embedding store
- MemoryManager (services/memory/memory_manager.py) — PostgreSQL+external provider router

The provider-routing sub-layer (prefetch, sync, entity CRUD, health_check) is now
accessible via the ``provider`` property, keeping the two concerns clearly separated
within a single canonical class.
"""

import asyncio
import gc
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

from .agent_diary import AgentDiaryService
from .cache import LRUCacheManager
from .enums import MemoryCategory, StorageStrategy, TaskPriority, TaskStatus
from .essential_story import EssentialStoryGenerator
from .models import MemoryEntry, TaskExecutionRecord
from .monitor import MemoryMonitor
from .protocols import ICacheManager, IGeneralStorage, ITaskStorage
from .storage import GeneralStorage, TaskStorage
from .working_memory import WorkingMemoryService

logger = get_logger(__name__)


class _ProviderRouter:
    """
    Provider-routing sub-layer (folded in from services/memory/MemoryManager).

    Routes entity/knowledge-graph operations to a built-in PostgreSQL provider
    and an optional external provider (Redis or Milvus).  Accessible as
    ``MemoryManager.provider``.
    """

    def __init__(self) -> None:
        # Lazy-import to avoid hard-dep on postgres/external at construction time
        from services.memory.postgres_provider import PostgresMemoryProvider

        self.built_in: PostgresMemoryProvider = PostgresMemoryProvider()
        self.external: Any | None = None
        self.external_enabled: bool = False

    async def initialize(self) -> None:
        from services.memory.external_provider_factory import ExternalProviderFactory

        try:
            await self.built_in.initialize()
            logger.info("Built-in PostgreSQL memory provider initialized")
            try:
                self.external = await ExternalProviderFactory.get_provider()
                if self.external:
                    self.external_enabled = True
                    logger.info("External memory provider initialized")
            except Exception as exc:
                logger.warning("External memory provider unavailable, using built-in only: %s", exc)
                self.external = None
                self.external_enabled = False
        except Exception as exc:
            logger.error("Failed to initialize provider router: %s", exc)
            raise

    async def close(self) -> None:
        from services.memory.external_provider_factory import ExternalProviderFactory

        try:
            if self.built_in:
                await self.built_in.close()
            if self.external:
                await self.external.close()
            await ExternalProviderFactory.close()
            logger.info("Provider router closed")
        except Exception as exc:
            logger.error("Error closing provider router: %s", exc)

    async def prefetch(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if self.external_enabled and self.external:
            try:
                result = await self.external.prefetch(context)
                if result:
                    return result
            except Exception as exc:
                logger.warning("External provider prefetch failed, falling back to built-in: %s", exc)
        try:
            return await self.built_in.prefetch(context)
        except Exception as exc:
            logger.error("Built-in provider prefetch failed: %s", exc)
            return {}

    async def sync(self, turn: Dict[str, Any]) -> None:
        try:
            await self.built_in.sync(turn)
        except Exception as exc:
            logger.error("Built-in provider sync failed: %s", exc)
            raise
        if self.external_enabled and self.external:
            try:
                await self.external.sync(turn)
            except Exception as exc:
                logger.warning("External provider sync failed, continuing: %s", exc)

    async def search(
        self, query: str, limit: int = 10, filters: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        if self.external_enabled and self.external:
            try:
                results = await self.external.search(query, limit, filters)
                if results:
                    return results
            except Exception as exc:
                logger.warning("External provider search failed, falling back to built-in: %s", exc)
        try:
            return await self.built_in.search(query, limit, filters)
        except Exception as exc:
            logger.error("Built-in provider search failed: %s", exc)
            return []

    async def get_entity(self, entity_id: str) -> Dict[str, Any] | None:
        try:
            return await self.built_in.get_entity(entity_id)
        except Exception as exc:
            logger.error("Error getting entity: %s", exc)
            return None

    async def update_entity(self, entity_id: str, updates: Dict[str, Any]) -> None:
        try:
            await self.built_in.update_entity(entity_id, updates)
        except Exception as exc:
            logger.error("Built-in provider update failed: %s", exc)
            raise
        if self.external_enabled and self.external:
            try:
                await self.external.update_entity(entity_id, updates)
            except Exception as exc:
                logger.warning("External provider update failed: %s", exc)

    async def delete_entity(self, entity_id: str) -> None:
        try:
            await self.built_in.delete_entity(entity_id)
        except Exception as exc:
            logger.error("Built-in provider delete failed: %s", exc)
            raise
        if self.external_enabled and self.external:
            try:
                await self.external.delete_entity(entity_id)
            except Exception as exc:
                logger.warning("External provider delete failed: %s", exc)

    async def health_check(self) -> Dict[str, bool]:
        health: Dict[str, bool] = {}
        try:
            health["built_in"] = await self.built_in.health_check()
        except Exception as exc:
            logger.error("Built-in health check failed: %s", exc)
            health["built_in"] = False
        if self.external_enabled and self.external:
            try:
                health["external"] = await self.external.health_check()
            except Exception as exc:
                logger.warning("External health check failed: %s", exc)
                health["external"] = False
        return health


class MemoryManager:
    """
    Memory Manager — canonical single memory manager for AutoBot.

    Combines features from 5 memory managers into a single, reusable,
    SOLID-principles-based implementation, and folds in the provider-routing
    sub-layer (formerly services/memory/MemoryManager) as the ``provider`` property.

    Features:
    - Task execution history (from enhanced_memory_manager.py)
    - General purpose memory (from memory_manager.py)
    - LRU caching (from optimized_memory_manager.py)
    - Memory monitoring (from optimized_memory_manager.py)
    - Unified storage API with strategy pattern
    - Provider routing: PostgreSQL + external (Redis/Milvus) via ``provider``
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
        >>> # Task execution
        >>> manager = MemoryManager()
        >>> record = TaskExecutionRecord(
        ...     task_id="task-001",
        ...     task_name="Process Document",
        ...     status=TaskStatus.PENDING,
        ...     priority=TaskPriority.HIGH,
        ...     created_at=datetime.now(tz=timezone.utc)
        ... )
        >>> await manager.log_task(record)

        >>> # General memory
        >>> await manager.store_memory(
        ...     MemoryCategory.FACT,
        ...     "AutoBot supports multi-modal AI",
        ...     metadata={"source": "documentation"}
        ... )

        >>> # Provider-routing (entity graph)
        >>> await manager.provider.initialize()
        >>> results = await manager.provider.search("machine learning")
    """

    def __init__(
        self,
        db_path: str = "data/unified_memory.db",
        enable_cache: bool = True,
        enable_monitoring: bool = False,
        cache_size: int = 1000,
        retention_days: int = 90,
        task_storage: ITaskStorage | None = None,
        general_storage: IGeneralStorage | None = None,
        cache_manager: ICacheManager | None = None,
        monitor: MemoryMonitor | None = None,
    ):
        """
        Initialize Memory Manager.

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
        self._cache = cache_manager or (LRUCacheManager(max_size=cache_size) if enable_cache else None)
        self._monitor = monitor or (MemoryMonitor() if enable_monitoring else None)

        # Database initialization flag and lock (thread-safe lazy initialization)
        self._initialized = False
        self._init_lock = asyncio.Lock()

        # Session-scoped short-term memory (Redis-backed, eagerly created)
        self._working_memory: WorkingMemoryService = WorkingMemoryService()

        # Lazily-instantiated subsystems
        self._essential_story: EssentialStoryGenerator | None = None
        self._agent_diary: AgentDiaryService | None = None

        # Provider-routing sub-layer (lazily instantiated on first access)
        self._provider: _ProviderRouter | None = None

        logger.info("Memory Manager created at %s", self.db_path)

    async def _ensure_initialized(self):
        """
        Ensure database is initialized (thread-safe lazy initialization).

        Uses double-check locking to prevent race conditions when multiple
        concurrent calls attempt to initialize the database simultaneously.
        """
        if not self._initialized:
            async with self._init_lock:
                if not self._initialized:
                    await self._init_database()
                    self._initialized = True

    async def _init_database(self):
        """Initialize database schema."""
        await asyncio.gather(
            self._task_storage.initialize(),
            self._general_storage.initialize(),
        )

    # ========================================================================
    # TASK-SPECIFIC API (from enhanced_memory_manager.py)
    # ========================================================================

    async def log_task(self, record: TaskExecutionRecord) -> str:
        """
        Log task execution record (async).

        Args:
            record: TaskExecutionRecord to log

        Returns:
            task_id of logged record

        Raises:
            ValueError: If task_id or task_name is empty
        """
        if not record.task_id or not record.task_id.strip():
            raise ValueError("task_id cannot be empty")
        if not record.task_name or not record.task_name.strip():
            raise ValueError("task_name cannot be empty")
        await self._ensure_initialized()
        return await self._task_storage.log_task(record)

    def log_task_sync(self, record: TaskExecutionRecord) -> str:
        """
        Log task execution record (sync wrapper).

        Backward compatibility wrapper for synchronous code.
        For async code, prefer: await manager.log_task(record)
        """
        from autobot_shared.async_compat import run_or_schedule

        return run_or_schedule(self.log_task(record))

    async def update_task_status(self, task_id: str, status: TaskStatus, **kwargs) -> bool:
        """
        Update task status and optional fields.

        Args:
            task_id: Task identifier
            status: New task status
            **kwargs: Additional fields — started_at, completed_at,
                      duration_seconds, error_message, outputs, retry_count

        Returns:
            True if updated, False otherwise

        Raises:
            ValueError: If task_id is empty or invalid kwargs provided
        """
        if not task_id or not task_id.strip():
            raise ValueError("task_id cannot be empty")
        if "duration_seconds" in kwargs and kwargs["duration_seconds"] < 0:
            raise ValueError("duration_seconds cannot be negative")
        if "retry_count" in kwargs and kwargs["retry_count"] < 0:
            raise ValueError("retry_count cannot be negative")
        await self._ensure_initialized()
        return await self._task_storage.update_task(task_id, status=status, **kwargs)

    async def get_task(self, task_id: str) -> TaskExecutionRecord | None:
        """Retrieve single task by ID."""
        await self._ensure_initialized()
        return await self._task_storage.get_task(task_id)

    async def get_task_history(
        self,
        agent_type: str | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
    ) -> List[TaskExecutionRecord]:
        """Query task execution history with filters."""
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

    async def get_task_statistics(self, days_back: int | None = None) -> Dict[str, Any]:
        """
        Get task execution statistics.

        Args:
            days_back: Unused filter parameter (kept for API compatibility).

        Returns:
            Dictionary with total_tasks, by_status, by_priority.
        """
        await self._ensure_initialized()
        return await self._task_storage.get_stats()

    # ========================================================================
    # GENERAL PURPOSE API (from memory_manager.py)
    # ========================================================================

    async def store_memory(
        self,
        category: MemoryCategory | str,
        content: str,
        metadata: Dict | None = None,
        reference_path: str | None = None,
        embedding: bytes | None = None,
    ) -> int:
        """
        Store general purpose memory entry.

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
            timestamp=datetime.now(tz=timezone.utc),
            reference_path=reference_path,
            embedding=embedding,
        )
        return await self._general_storage.store(entry)

    async def retrieve_memories(
        self,
        category: MemoryCategory | str,
        limit: int = 100,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        reference_path: str | None = None,
    ) -> List[MemoryEntry]:
        """
        Retrieve memories by category and filters.

        Raises:
            ValueError: If limit is invalid or date range is invalid
        """
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
        """Search memories by content or metadata."""
        await self._ensure_initialized()
        return await self._general_storage.search(query)

    async def cleanup_old_memories(self, retention_days: int | None = None) -> int:
        """Remove memories older than retention period. Returns number deleted."""
        await self._ensure_initialized()
        days = retention_days or self.retention_days
        return await self._general_storage.cleanup_old(days)

    # ========================================================================
    # CACHING API (from optimized_memory_manager.py)
    # ========================================================================

    def cache_get(self, key: str) -> Any | None:
        """Get item from cache. Returns None if cache disabled or key missing."""
        if not self._cache:
            return None
        return self._cache.get(key)

    def cache_put(self, key: str, value: Any) -> None:
        """Put item in cache."""
        if self._cache:
            self._cache.put(key, value)

    def cache_evict(self, count: int) -> int:
        """Evict oldest items from cache. Returns number evicted."""
        if not self._cache:
            return 0
        return self._cache.evict(count)

    def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics (enabled, size, max_size, hits, misses, hit_rate)."""
        if not self._cache:
            return {"enabled": False}
        return self._cache.stats()

    # ========================================================================
    # UNIFIED STORAGE API (Strategy Pattern)
    # ========================================================================

    async def _store_task_execution(self, data: Any) -> str:
        """Store data using task execution strategy.

        Raises:
            TypeError: If data is not a TaskExecutionRecord
        """
        if not isinstance(data, TaskExecutionRecord):
            raise TypeError("TASK_EXECUTION strategy requires TaskExecutionRecord")
        return await self.log_task(data)

    async def _store_general_memory(self, data: Any) -> int:
        """Store data using general memory strategy.

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
        """Store data using cache strategy. Returns cache key."""
        key = hashlib.sha256(str(data).encode()).hexdigest()[:16]
        self.cache_put(key, data)
        return key

    async def store(
        self,
        data: TaskExecutionRecord | MemoryEntry | Any,
        strategy: StorageStrategy = StorageStrategy.TASK_EXECUTION,
    ) -> str | int:
        """
        Unified storage interface with strategy pattern.

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
    # MEMORY SUBSYSTEM PROPERTIES
    # Agents access subsystems via these properties so they never need to
    # import WorkingMemoryService, EssentialStoryGenerator, AgentDiaryService,
    # or _ProviderRouter directly.
    # ========================================================================

    @property
    def working_memory(self) -> WorkingMemoryService:
        """Redis-backed session-scoped short-term memory (eager, TTL-backed)."""
        return self._working_memory

    @property
    def essential_story(self) -> EssentialStoryGenerator:
        """Always-loaded compact memory summary generator (lazy-init)."""
        if self._essential_story is None:
            self._essential_story = EssentialStoryGenerator()
        return self._essential_story

    @property
    def agent_diary(self) -> AgentDiaryService:
        """Per-agent cross-session journal backed by the knowledge base (lazy-init)."""
        if self._agent_diary is None:
            self._agent_diary = AgentDiaryService()
        return self._agent_diary

    @property
    def provider(self) -> _ProviderRouter:
        """Provider-routing sub-layer: PostgreSQL + external (Redis/Milvus) entity graph.

        Exposes: initialize(), close(), prefetch(), sync(), search(),
                 get_entity(), update_entity(), delete_entity(), health_check().
        Call ``await manager.provider.initialize()`` before use.
        """
        if self._provider is None:
            self._provider = _ProviderRouter()
        return self._provider

    # ========================================================================
    # STATISTICS & MONITORING
    # ========================================================================

    async def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics (task, general, cache, system)."""
        await self._ensure_initialized()
        stats = {
            "task_storage": await self._task_storage.get_stats(),
            "general_storage": await self._general_storage.get_stats(),
            "cache": self.cache_stats(),
        }
        if self._monitor:
            stats["system_memory"] = self._monitor.get_usage()
        return stats

    def get_memory_usage(self) -> Dict[str, Any] | None:
        """Get current system memory usage. Returns None if monitoring disabled."""
        if not self._monitor:
            return None
        return self._monitor.get_usage()

    async def adaptive_cleanup(self, memory_threshold: float = 0.8) -> Dict[str, int]:
        """
        Perform adaptive cleanup based on memory pressure.

        Args:
            memory_threshold: Memory usage threshold (0.0-1.0)

        Returns:
            Dictionary with cache_evicted and memories_deleted counts.
        """
        await self._ensure_initialized()
        cleanup_counts = {"cache_evicted": 0, "memories_deleted": 0}
        if self._monitor and self._monitor.should_cleanup(memory_threshold):
            logger.info("Memory pressure detected, performing adaptive cleanup")
            if self._cache:
                cache_size = self._cache.stats()["size"]
                evict_count = int(cache_size * 0.2)
                cleanup_counts["cache_evicted"] = self.cache_evict(evict_count)
            cleanup_counts["memories_deleted"] = await self.cleanup_old_memories()
            gc.collect()
            logger.info("Cleanup completed: %s", cleanup_counts)
        return cleanup_counts

    # ========================================================================
    # SYNC CONVENIENCE API (migrated from EnhancedMemoryManager compat #10572)
    # ========================================================================

    def _run_sync(self, coro):
        """Run an async coroutine synchronously via the shared run_or_schedule helper."""
        from autobot_shared.async_compat import run_or_schedule

        return run_or_schedule(coro)

    def create_task_record(
        self,
        task_name: str,
        description: str,
        priority: "TaskPriority | None" = None,
        agent_type: str | None = None,
        inputs: Dict | None = None,
        parent_task_id: str | None = None,
        metadata: Dict | None = None,
    ) -> str:
        """Create a task record and return its task_id (sync wrapper).

        Generates a deterministic task_id from task_name + current UTC timestamp.
        Do NOT call from async code — use await log_task() instead.
        """
        import hashlib as _hashlib

        from .enums import TaskPriority as _TP
        from .enums import TaskStatus

        task_id = _hashlib.sha256(
            f"{task_name}_{datetime.now(tz=timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]
        record = TaskExecutionRecord(
            task_id=task_id,
            task_name=task_name,
            description=description,
            status=TaskStatus.PENDING,
            priority=priority or _TP.MEDIUM,
            created_at=datetime.now(tz=timezone.utc),
            agent_type=agent_type,
            inputs=inputs,
            parent_task_id=parent_task_id,
            metadata=metadata,
        )
        self.log_task_sync(record)
        logger.info("Created task record: %s - %s", task_id, task_name)
        return task_id

    def start_task(self, task_id: str) -> bool:
        """Mark task as started (sync wrapper). Do NOT call from async code."""
        from .enums import TaskStatus

        result = self._run_sync(
            self.update_task_status(task_id, TaskStatus.IN_PROGRESS, started_at=datetime.now(tz=timezone.utc))
        )
        if result:
            logger.info("Started task: %s", task_id)
        else:
            logger.warning("Task not found for start: %s", task_id)
        return result

    def complete_task(self, task_id: str, outputs: Dict | None = None, status=None) -> bool:
        """Mark task as completed (sync wrapper). Do NOT call from async code."""
        from .enums import TaskStatus

        final_status = status or TaskStatus.COMPLETED
        task = self._run_sync(self.get_task(task_id))
        if not task:
            logger.warning("Task not found for completion: %s", task_id)
            return False
        completed_at = datetime.now(tz=timezone.utc)
        duration = (completed_at - task.started_at).total_seconds() if task.started_at else None
        result = self._run_sync(
            self.update_task_status(
                task_id, final_status, completed_at=completed_at, duration_seconds=duration, outputs=outputs
            )
        )
        if result:
            logger.info("Completed task: %s (duration: %ss)", task_id, duration)
        return result

    def fail_task(self, task_id: str, error_message: str, retry_count: int = 0) -> bool:
        """Mark task as failed (sync wrapper). Do NOT call from async code."""
        from .enums import TaskStatus

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

    def add_markdown_reference(
        self,
        task_id: str,
        markdown_file_path: str,
        reference_type: str = "documentation",
    ) -> bool:
        """Store a markdown-file reference against a task (sync wrapper).

        Do NOT call from async code — use await store_memory() directly instead.
        """
        from .enums import MemoryCategory

        content = f"task:{task_id} file:{markdown_file_path} type:{reference_type}"
        metadata = {
            "task_id": task_id,
            "markdown_file_path": markdown_file_path,
            "reference_type": reference_type,
        }
        self._run_sync(
            self.store_memory(
                MemoryCategory.FACT,
                content,
                metadata=metadata,
                reference_path=markdown_file_path,
            )
        )
        logger.info("Added markdown reference for task %s: %s", task_id, markdown_file_path)
        return True

    def _get_embedding_cache_size(self) -> int:
        """Return current LRU cache occupancy. Returns 0 when caching is disabled."""
        stats = self.cache_stats()
        return int(stats.get("size", 0))

    def cleanup_old_data(self, days_to_keep: int = 90) -> Dict[str, Any]:
        """Remove records older than days_to_keep (sync wrapper).

        Returns: {"tasks_deleted": N, "embeddings_deleted": 0}
        Do NOT call from async code — use await cleanup_old_memories() directly.
        """
        deleted = self._run_sync(self.cleanup_old_memories(days_to_keep))
        result: Dict[str, Any] = {"tasks_deleted": deleted, "embeddings_deleted": 0}
        logger.info("cleanup_old_data completed: %s", result)
        return result

    def log_task_execution(self, record: "TaskExecutionRecord") -> str:
        """Alias for log_task_sync (sync wrapper, backward compatibility).

        Do NOT call from async code — use await log_task() instead.
        """
        return self.log_task_sync(record)

    def get_task_history_sync(
        self,
        agent_type: str | None = None,
        status: "TaskStatus | None" = None,
        limit: int = 100,
        days_back: int = 30,
    ) -> List:
        """Query task history synchronously (sync wrapper).

        Do NOT call from async code — use await get_task_history() instead.
        """
        from datetime import timedelta

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

    def get_task_statistics_sync(self, days_back: int | None = None) -> Dict[str, Any]:
        """Return task execution statistics synchronously (sync wrapper).

        Do NOT call from async code — use await get_task_statistics() instead.
        """
        return self._run_sync(self.get_task_statistics(days_back))

    def store_embedding(
        self,
        content: str,
        content_type: str,
        embedding_model: str,
        embedding_vector: List[float],
    ) -> bool:
        """Persist an embedding vector as a general memory entry (sync wrapper).

        Do NOT call from async code — use await store_memory() directly instead.
        """
        import json as _json

        from .enums import MemoryCategory

        metadata = {
            "content_type": content_type,
            "embedding_model": embedding_model,
            "vector_length": len(embedding_vector),
        }
        embedding_bytes = _json.dumps(embedding_vector).encode("utf-8")
        self._run_sync(
            self.store_memory(
                MemoryCategory.FACT,
                content,
                metadata=metadata,
                embedding=embedding_bytes,
            )
        )
        logger.debug("Stored embedding for content_type=%s model=%s", content_type, embedding_model)
        return True


__all__ = ["MemoryManager"]
