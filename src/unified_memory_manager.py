# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Memory Manager for AutoBot - Phase 5 Consolidation

Consolidates 5 memory manager implementations (2,831 lines) into a single,
reusable, SOLID-principles-based unified manager (~1,300 lines).

Combines features from:
- enhanced_memory_manager.py: Task execution history (7 files depend on this)
- memory_manager.py: General purpose memory (2 files depend on this)
- optimized_memory_manager.py: LRU caching & monitoring (unused, integrated here)

Design Principles Applied:
1. Single Responsibility: Each component has ONE job
2. Interface Segregation: Multiple protocols for different use cases
3. Dependency Injection: Components injectable via constructor
4. Strategy Pattern: Unified store() method with StorageStrategy enum
5. Composition over Inheritance: Components composed, not inherited
6. Async-First: All public methods async, sync wrappers provided
7. DRY: Single implementation (no separate sync/async files)
8. Open/Closed: Open for extension, closed for modification
9. Backward Compatibility: Wrappers preserve existing APIs

Author: AutoBot Backend Team
Date: 2025-11-11
"""

import asyncio
import gc
import hashlib
import json
import logging
import os
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Union

import aiosqlite

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available - memory monitoring disabled")

from src.constants.network_constants import NetworkConstants
from src.utils.common import PathUtils
from src.utils.database_pool import get_connection_pool

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS - Shared across all storage strategies
# ============================================================================


class TaskStatus(Enum):
    """Task execution status enumeration"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class TaskPriority(Enum):
    """Task priority levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MemoryCategory(Enum):
    """General purpose memory categories"""

    TASK = "task"
    EXECUTION = "execution"
    STATE = "state"
    CONFIG = "config"
    FACT = "fact"
    CONVERSATION = "conversation"
    CUSTOM = "custom"


class StorageStrategy(Enum):
    """Storage strategies for unified store() method"""

    TASK_EXECUTION = "task_execution"  # Task-centric storage
    GENERAL_MEMORY = "general_memory"  # Category-based storage
    CACHED = "cached"  # LRU cache only


# ============================================================================
# DATA MODELS - Structured data classes
# ============================================================================


@dataclass
class TaskExecutionRecord:
    """
    Task-centric memory record (from enhanced_memory_manager)

    Comprehensive task execution tracking with:
    - Lifecycle management (pending → in_progress → completed)
    - Duration tracking
    - Agent attribution
    - Input/output logging
    - Error handling
    - Parent/child relationships
    - Markdown references
    """

    task_id: str
    task_name: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    agent_type: Optional[str] = None
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    markdown_references: Optional[List[str]] = None
    parent_task_id: Optional[str] = None
    subtask_ids: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MemoryEntry:
    """
    General purpose memory entry (from memory_manager)

    Category-based memory storage with:
    - Flexible categorization
    - Metadata support
    - Optional embedding storage
    - Reference path tracking
    """

    id: Optional[int]
    category: Union[MemoryCategory, str]
    content: str
    metadata: Dict[str, Any]
    timestamp: datetime
    reference_path: Optional[str] = None
    embedding: Optional[bytes] = None


# ============================================================================
# PROTOCOLS - Interface Segregation Principle
# ============================================================================


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

    async def get_task(self, task_id: str) -> Optional[TaskExecutionRecord]:
        """Retrieve single task by ID"""
        ...

    async def get_task_history(
        self, filters: Dict[str, Any]
    ) -> List[TaskExecutionRecord]:
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
    """

    async def store(self, entry: MemoryEntry) -> int:
        """Store a memory entry"""
        ...

    async def retrieve(
        self, category: Union[MemoryCategory, str], filters: Dict[str, Any]
    ) -> List[MemoryEntry]:
        """Retrieve memories by category and filters"""
        ...

    async def search(self, query: str) -> List[MemoryEntry]:
        """Search memories by content/metadata"""
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

    def get(self, key: str) -> Optional[Any]:
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


# ============================================================================
# COMPONENT IMPLEMENTATIONS - Single Responsibility Principle
# ============================================================================


class TaskStorage:
    """
    Task-specific storage implementation (ITaskStorage)

    Responsibility: Manage task execution history in SQLite database
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self):
        """Get database connection context manager"""
        return aiosqlite.connect(self.db_path)

    async def initialize(self):
        """Initialize task execution history table"""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_execution_history (
                    task_id TEXT PRIMARY KEY,
                    task_name TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    duration_seconds REAL,
                    agent_type TEXT,
                    inputs_json TEXT,
                    outputs_json TEXT,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    markdown_references_json TEXT,
                    parent_task_id TEXT,
                    subtask_ids_json TEXT,
                    metadata_json TEXT
                )
            """
            )

            # Indexes for common queries
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_status
                ON task_execution_history(status)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_created
                ON task_execution_history(created_at)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_agent
                ON task_execution_history(agent_type)
            """
            )

            await conn.commit()

    async def log_task(self, record: TaskExecutionRecord) -> str:
        """Log task execution record"""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO task_execution_history (
                    task_id, task_name, description, status, priority,
                    created_at, started_at, completed_at, duration_seconds,
                    agent_type, inputs_json, outputs_json, error_message,
                    retry_count, markdown_references_json, parent_task_id,
                    subtask_ids_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    record.task_id,
                    record.task_name,
                    record.description,
                    record.status.value,
                    record.priority.value,
                    record.created_at,
                    record.started_at,
                    record.completed_at,
                    record.duration_seconds,
                    record.agent_type,
                    json.dumps(record.inputs) if record.inputs else None,
                    json.dumps(record.outputs) if record.outputs else None,
                    record.error_message,
                    record.retry_count,
                    (
                        json.dumps(record.markdown_references)
                        if record.markdown_references
                        else None
                    ),
                    record.parent_task_id,
                    json.dumps(record.subtask_ids) if record.subtask_ids else None,
                    json.dumps(record.metadata) if record.metadata else None,
                ),
            )
            await conn.commit()

        logger.debug(f"Logged task: {record.task_id} ({record.status.value})")
        return record.task_id

    async def update_task(self, task_id: str, **updates) -> bool:
        """Update task fields dynamically"""
        if not updates:
            return False

        # Build dynamic UPDATE query
        set_clauses = []
        values = []

        for key, value in updates.items():
            if key == "status" and isinstance(value, TaskStatus):
                set_clauses.append("status = ?")
                values.append(value.value)
            elif key == "priority" and isinstance(value, TaskPriority):
                set_clauses.append("priority = ?")
                values.append(value.value)
            elif key in [
                "inputs",
                "outputs",
                "metadata",
                "markdown_references",
                "subtask_ids",
            ]:
                set_clauses.append(f"{key}_json = ?")
                values.append(json.dumps(value) if value else None)
            elif key in ["started_at", "completed_at"]:
                set_clauses.append(f"{key} = ?")
                values.append(value)
            elif key in [
                "duration_seconds",
                "retry_count",
                "error_message",
                "agent_type",
            ]:
                set_clauses.append(f"{key} = ?")
                values.append(value)

        if not set_clauses:
            return False

        query = f"UPDATE task_execution_history SET {', '.join(set_clauses)} WHERE task_id = ?"
        values.append(task_id)

        async with self._get_connection() as conn:
            cursor = await conn.execute(query, values)
            await conn.commit()
            return cursor.rowcount > 0

    async def get_task(self, task_id: str) -> Optional[TaskExecutionRecord]:
        """Retrieve single task by ID"""
        async with self._get_connection() as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM task_execution_history WHERE task_id = ?", (task_id,)
            ),
            row = await cursor.fetchone()

            if not row:
                return None

            return self._row_to_record(row)

    async def get_task_history(
        self, filters: Dict[str, Any]
    ) -> List[TaskExecutionRecord]:
        """Query task history with filters"""
        where_clauses = []
        values = []

        if filters.get("agent_type"):
            where_clauses.append("agent_type = ?")
            values.append(filters["agent_type"])

        if filters.get("status"):
            status = filters["status"]
            where_clauses.append("status = ?")
            values.append(status.value if isinstance(status, TaskStatus) else status)

        if filters.get("priority"):
            priority = filters["priority"]
            where_clauses.append("priority = ?")
            values.append(
                priority.value if isinstance(priority, TaskPriority) else priority
            )

        if filters.get("start_date"):
            where_clauses.append("created_at >= ?")
            values.append(filters["start_date"])

        if filters.get("end_date"):
            where_clauses.append("created_at <= ?")
            values.append(filters["end_date"])

        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        limit = filters.get("limit", 100)

        query = f"""
            SELECT * FROM task_execution_history
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
        """
        values.append(limit)

        async with self._get_connection() as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(query, values)
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    async def get_stats(self) -> Dict[str, Any]:
        """Get task storage statistics"""
        async with self._get_connection() as conn:
            conn.row_factory = aiosqlite.Row
            # Total tasks
            cursor = await conn.execute("SELECT COUNT(*) FROM task_execution_history")
            total = (await cursor.fetchone())[0]

            # Tasks by status
            cursor = await conn.execute(
                """
                SELECT status, COUNT(*)
                FROM task_execution_history
                GROUP BY status
            """
            ),
            by_status = {row[0]: row[1] for row in await cursor.fetchall()}

            # Tasks by priority
            cursor = await conn.execute(
                """
                SELECT priority, COUNT(*)
                FROM task_execution_history
                GROUP BY priority
            """
            ),
            by_priority = {row[0]: row[1] for row in await cursor.fetchall()}

            return {
                "total_tasks": total,
                "by_status": by_status,
                "by_priority": by_priority,
            }

    def _row_to_record(self, row: aiosqlite.Row) -> TaskExecutionRecord:
        """Convert database row to TaskExecutionRecord"""
        return TaskExecutionRecord(
            task_id=row["task_id"],
            task_name=row["task_name"],
            description=row["description"],
            status=TaskStatus(row["status"]),
            priority=TaskPriority(row["priority"]),
            created_at=(
                datetime.fromisoformat(row["created_at"])
                if isinstance(row["created_at"], str)
                else row["created_at"]
            ),
            started_at=(
                datetime.fromisoformat(row["started_at"])
                if row["started_at"] and isinstance(row["started_at"], str)
                else row["started_at"]
            ),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"] and isinstance(row["completed_at"], str)
                else row["completed_at"]
            ),
            duration_seconds=row["duration_seconds"],
            agent_type=row["agent_type"],
            inputs=json.loads(row["inputs_json"]) if row["inputs_json"] else None,
            outputs=json.loads(row["outputs_json"]) if row["outputs_json"] else None,
            error_message=row["error_message"],
            retry_count=row["retry_count"],
            markdown_references=(
                json.loads(row["markdown_references_json"])
                if row["markdown_references_json"]
                else None
            ),
            parent_task_id=row["parent_task_id"],
            subtask_ids=(
                json.loads(row["subtask_ids_json"]) if row["subtask_ids_json"] else None
            ),
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else None,
        )


class GeneralStorage:
    """
    General purpose storage implementation (IGeneralStorage)

    Responsibility: Manage category-based memory in SQLite database
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self):
        """Get database connection context manager"""
        return aiosqlite.connect(self.db_path)

    async def initialize(self):
        """Initialize memory entries table"""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    timestamp TIMESTAMP NOT NULL,
                    reference_path TEXT,
                    embedding BLOB
                )
            """
            )

            # Indexes for common queries
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_category
                ON memory_entries(category)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_timestamp
                ON memory_entries(timestamp)
            """
            )

            await conn.commit()

    async def store(self, entry: MemoryEntry) -> int:
        """Store memory entry"""
        category_value = (
            entry.category.value
            if isinstance(entry.category, MemoryCategory)
            else entry.category
        )

        async with self._get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO memory_entries (
                    category, content, metadata_json, timestamp,
                    reference_path, embedding
                ) VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    category_value,
                    entry.content,
                    json.dumps(entry.metadata) if entry.metadata else None,
                    entry.timestamp,
                    entry.reference_path,
                    entry.embedding,
                ),
            )
            await conn.commit()

            logger.debug(
                f"Stored memory entry: {category_value} (ID: {cursor.lastrowid})"
            )
            return cursor.lastrowid

    async def retrieve(
        self, category: Union[MemoryCategory, str], filters: Dict[str, Any]
    ) -> List[MemoryEntry]:
        """Retrieve memories by category and filters"""
        category_value = (
            category.value if isinstance(category, MemoryCategory) else category
        )

        where_clauses = ["category = ?"]
        values = [category_value]

        if filters.get("start_date"):
            where_clauses.append("timestamp >= ?")
            values.append(filters["start_date"])

        if filters.get("end_date"):
            where_clauses.append("timestamp <= ?")
            values.append(filters["end_date"])

        if filters.get("reference_path"):
            where_clauses.append("reference_path = ?")
            values.append(filters["reference_path"])

        limit = filters.get("limit", 100)

        query = f"""
            SELECT * FROM memory_entries
            WHERE {' AND '.join(where_clauses)}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        values.append(limit)

        async with self._get_connection() as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(query, values)
            rows = await cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]

    async def search(self, query: str) -> List[MemoryEntry]:
        """Search memories by content or metadata"""
        async with self._get_connection() as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT * FROM memory_entries
                WHERE content LIKE ? OR metadata_json LIKE ?
                ORDER BY timestamp DESC
                LIMIT 100
            """,
                (f"%{query}%", f"%{query}%"),
            )

            rows = await cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]

    async def cleanup_old(self, retention_days: int) -> int:
        """Remove entries older than retention period"""
        cutoff = datetime.now() - timedelta(days=retention_days)

        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM memory_entries WHERE timestamp < ?", (cutoff,)
            )
            await conn.commit()

            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(
                    f"Cleaned up {deleted} old memory entries (>{retention_days} days)"
                )

            return deleted

    async def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        async with self._get_connection() as conn:
            conn.row_factory = aiosqlite.Row
            # Total entries
            cursor = await conn.execute("SELECT COUNT(*) FROM memory_entries")
            total = (await cursor.fetchone())[0]

            # Entries by category
            cursor = await conn.execute(
                """
                SELECT category, COUNT(*)
                FROM memory_entries
                GROUP BY category
            """
            ),
            by_category = {row[0]: row[1] for row in await cursor.fetchall()}

            return {"total_entries": total, "by_category": by_category}

    def _row_to_entry(self, row: aiosqlite.Row) -> MemoryEntry:
        """Convert database row to MemoryEntry"""
        return MemoryEntry(
            id=row["id"],
            category=row["category"],
            content=row["content"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
            timestamp=(
                datetime.fromisoformat(row["timestamp"])
                if isinstance(row["timestamp"], str)
                else row["timestamp"]
            ),
            reference_path=row["reference_path"],
            embedding=row["embedding"],
        )


class LRUCacheManager:
    """
    LRU cache implementation (ICacheManager)

    Responsibility: Provide in-memory LRU caching with statistics
    """

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache: OrderedDict = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get item from cache"""
        if key in self.cache:
            # Move to end (most recently used)
            value = self.cache.pop(key)
            self.cache[key] = value
            self.hits += 1
            return value
        else:
            self.misses += 1
            return None

    def put(self, key: str, value: Any) -> None:
        """Put item in cache with LRU eviction"""
        # Remove if exists
        if key in self.cache:
            self.cache.pop(key)

        # Add to end
        self.cache[key] = value

        # Enforce size limit
        while len(self.cache) > self.max_size:
            oldest_key = next(iter(self.cache))
            self.cache.pop(oldest_key)
            logger.debug(f"Evicted {oldest_key} from cache (LRU)")

    def evict(self, count: int) -> int:
        """Evict oldest N items"""
        evicted = 0
        while evicted < count and self.cache:
            oldest_key = next(iter(self.cache))
            self.cache.pop(oldest_key)
            evicted += 1

        return evicted

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.hits + self.misses
        hit_rate = self.hits / total_requests if total_requests > 0 else 0.0

        return {
            "enabled": True,
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
        }


class MemoryMonitor:
    """
    System memory monitoring component

    Responsibility: Monitor system memory usage (requires psutil)
    """

    def __init__(self):
        self.enabled = PSUTIL_AVAILABLE
        if not self.enabled:
            logger.warning("Memory monitoring disabled (psutil not available)")

    def get_usage(self) -> Optional[Dict[str, Any]]:
        """Get current system memory usage"""
        if not self.enabled:
            return None

        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            system_memory = psutil.virtual_memory()

            return {
                "process_rss_mb": memory_info.rss / (1024 * 1024),
                "process_vms_mb": memory_info.vms / (1024 * 1024),
                "system_percent": system_memory.percent,
                "system_available_mb": system_memory.available / (1024 * 1024),
            }
        except Exception as e:
            logger.error(f"Failed to get memory usage: {e}")
            return None

    def should_cleanup(self, threshold: float = 0.8) -> bool:
        """Check if cleanup is needed based on memory threshold"""
        if not self.enabled:
            return False

        usage = self.get_usage()
        if usage:
            return usage["system_percent"] > (threshold * 100)

        return False


# ============================================================================
# UNIFIED MEMORY MANAGER - Main Class
# ============================================================================


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

        logger.info(f"Unified Memory Manager created at {self.db_path}")

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
        await self._task_storage.initialize()
        await self._general_storage.initialize()

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

        ⚠️ WARNING: DO NOT call from async code - use log_task() instead.
        This uses asyncio.run() which creates a new event loop. It will fail
        if called from within an existing async context (RuntimeError: cannot
        be called from a running event loop).

        For async code, always use: await manager.log_task(record)
        """
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

    async def store(
        self,
        data: Union[TaskExecutionRecord, MemoryEntry, Any],
        strategy: StorageStrategy = StorageStrategy.TASK_EXECUTION,
    ) -> Union[str, int]:
        """
        Unified storage interface with strategy pattern

        This demonstrates code reusability by providing a single interface
        for different storage strategies.

        Args:
            data: Data to store (TaskExecutionRecord, MemoryEntry, or any)
            strategy: Storage strategy to use

        Returns:
            ID/key of stored data (type depends on strategy)

        Raises:
            TypeError: If data type doesn't match strategy
            ValueError: If strategy is unknown

        Example:
            >>> # Task strategy
            >>> task = TaskExecutionRecord(...)
            >>> task_id = await manager.store(task, StorageStrategy.TASK_EXECUTION)

            >>> # Memory strategy
            >>> entry = MemoryEntry(...)
            >>> entry_id = await manager.store(entry, StorageStrategy.GENERAL_MEMORY)

            >>> # Cache strategy
            >>> cache_key = await manager.store({"data": "test"}, StorageStrategy.CACHED)
        """
        await self._ensure_initialized()
        if strategy == StorageStrategy.TASK_EXECUTION:
            if not isinstance(data, TaskExecutionRecord):
                raise TypeError("TASK_EXECUTION strategy requires TaskExecutionRecord")
            return await self.log_task(data)

        elif strategy == StorageStrategy.GENERAL_MEMORY:
            if not isinstance(data, MemoryEntry):
                raise TypeError("GENERAL_MEMORY strategy requires MemoryEntry")
            return await self.store_memory(
                data.category,
                data.content,
                data.metadata,
                data.reference_path,
                data.embedding,
            )

        elif strategy == StorageStrategy.CACHED:
            # Generate cache key from data
            key = hashlib.sha256(str(data).encode()).hexdigest()[:16]
            self.cache_put(key, data)
            return key

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

            logger.info(f"Cleanup completed: {cleanup_counts}")

        return cleanup_counts


# ============================================================================
# BACKWARD COMPATIBILITY WRAPPERS
# ============================================================================


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


class LongTermMemoryManager:
    """
    Backward compatibility wrapper for memory_manager.py

    Used by 2 files:
    - src/orchestrator.py
    - analysis/refactoring/test_memory_path_utils.py
    """

    def __init__(
        self, config_path: Optional[str] = None, db_path: str = "data/agent_memory.db"
    ):
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
        logger.info(
            f"LongTermMemoryManager compatibility wrapper initialized at {db_path}"
        )

    async def store_memory(
        self,
        category: str,
        content: str,
        metadata: Optional[Dict] = None,
        embedding: Optional[bytes] = None,
    ) -> int:
        """Map old API to new unified API"""
        # Convert string category to enum if possible
        try:
            cat = MemoryCategory[category.upper()]
        except (KeyError, AttributeError):
            cat = category  # Use as-is if not in enum

        return await self._unified.store_memory(
            cat, content, metadata, embedding=embedding
        )

    async def retrieve_memories(
        self, category: str, filters: Optional[Dict] = None, limit: int = 100
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
        """Search by metadata (limited implementation)"""
        # Convert to content search
        query = " ".join(str(v) for v in metadata_query.values())
        return await self._unified.search_memories(query)

    async def cleanup_old_memories(self, retention_days: Optional[int] = None) -> int:
        """Cleanup old memories"""
        return await self._unified.cleanup_old_memories(retention_days)


# ============================================================================
# GLOBAL INSTANCES (for drop-in replacement)
# ============================================================================

# Lazy initialization - only create when first accessed
_enhanced_memory_instance = None
_long_term_memory_instance = None


def get_enhanced_memory_manager() -> EnhancedMemoryManager:
    """Get global EnhancedMemoryManager instance (singleton)"""
    global _enhanced_memory_instance
    if _enhanced_memory_instance is None:
        _enhanced_memory_instance = EnhancedMemoryManager()
    return _enhanced_memory_instance


def get_long_term_memory_manager() -> LongTermMemoryManager:
    """Get global LongTermMemoryManager instance (singleton)"""
    global _long_term_memory_instance
    if _long_term_memory_instance is None:
        _long_term_memory_instance = LongTermMemoryManager()
    return _long_term_memory_instance


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Enums
    "TaskStatus",
    "TaskPriority",
    "MemoryCategory",
    "StorageStrategy",
    # Data Models
    "TaskExecutionRecord",
    "MemoryEntry",
    # Protocols
    "ITaskStorage",
    "IGeneralStorage",
    "ICacheManager",
    # Components
    "TaskStorage",
    "GeneralStorage",
    "LRUCacheManager",
    "MemoryMonitor",
    # Main Manager
    "UnifiedMemoryManager",
    # Compatibility Wrappers
    "EnhancedMemoryManager",
    "LongTermMemoryManager",
    # Global Instances
    "get_enhanced_memory_manager",
    "get_long_term_memory_manager",
]
