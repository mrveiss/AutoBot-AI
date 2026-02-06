# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Async Enhanced Memory Manager for AutoBot Phase 7
Comprehensive task logging and execution history with aiosqlite and
markdown references
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task execution status enumeration"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Priority(Enum):
    """Task priority levels"""

    LOW = 1
    MEDIUM = 3
    HIGH = 5
    URGENT = 7
    CRITICAL = 9


# Alias for backward compatibility
TaskPriority = Priority

# Performance optimization: O(1) lookup for terminal task statuses (Issue #326)
TERMINAL_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}


@dataclass
class TaskEntry:
    """Enhanced task entry with comprehensive tracking"""

    task_id: str
    description: str
    status: TaskStatus
    priority: Priority
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    assigned_agent: Optional[str] = None
    parent_task_id: Optional[str] = None
    tags: List[str] = None
    metadata: Dict[str, Any] = None
    execution_log: List[Dict[str, Any]] = None
    estimated_duration_minutes: Optional[int] = None
    actual_duration_minutes: Optional[int] = None
    dependencies: List[str] = None
    markdown_reference: Optional[str] = None

    def __post_init__(self):
        """Initialize default empty collections for task entry fields."""
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}
        if self.execution_log is None:
            self.execution_log = []
        if self.dependencies is None:
            self.dependencies = []

    def to_db_tuple(self) -> tuple:
        """Convert to tuple for SQLite insertion (Issue #372 - reduces feature envy).

        Returns:
            Tuple with all fields formatted for tasks table insertion.
        """
        return (
            self.task_id,
            self.description,
            self.status.value,
            self.priority.value,
            self.created_at.timestamp(),
            self.updated_at.timestamp(),
            self.completed_at.timestamp() if self.completed_at else None,
            self.assigned_agent,
            self.parent_task_id,
            json.dumps(self.tags),
            json.dumps(self.metadata),
            json.dumps(self.execution_log),
            self.estimated_duration_minutes,
            self.actual_duration_minutes,
            json.dumps(self.dependencies),
            self.markdown_reference,
        )

    def generate_task_id(self) -> str:
        """Generate a unique task ID based on timestamp and description hash (Issue #372).

        Returns:
            Generated task ID string.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        desc_hash = hashlib.md5(
            self.description.encode(), usedforsecurity=False
        ).hexdigest()[:8]
        return f"task_{timestamp}_{desc_hash}"


@dataclass
class ExecutionRecord:
    """Individual execution step record"""

    record_id: Optional[str]
    task_id: str
    timestamp: datetime
    action: str
    result: str
    duration_ms: int
    success: bool
    error_message: Optional[str] = None
    agent_context: Dict[str, Any] = None

    def __post_init__(self):
        """Initialize default empty dict for agent context field."""
        if self.agent_context is None:
            self.agent_context = {}


class AsyncEnhancedMemoryManager:
    """Async enhanced memory manager with comprehensive task tracking"""

    def __init__(self, db_path: str = "data/enhanced_memory.db"):
        """Initialize async enhanced memory manager with database path and lock."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize async database setup
        self._initialized = False
        self._init_lock = asyncio.Lock()

        logger.info("Async Enhanced Memory Manager initialized: %s", self.db_path)

    async def _configure_pragmas(self, conn) -> None:
        """
        Configure SQLite pragmas for optimal performance.

        Issue #281: Extracted helper for PRAGMA configuration.
        """
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA cache_size=10000")
        await conn.execute("PRAGMA temp_store=MEMORY")
        await conn.execute("PRAGMA foreign_keys=ON")

    async def _create_tasks_table(self, conn) -> None:
        """
        Create tasks table with enhanced schema for task tracking.

        Issue #620.
        """
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                completed_at REAL,
                assigned_agent TEXT,
                parent_task_id TEXT,
                tags TEXT, -- JSON array
                metadata TEXT, -- JSON object
                execution_log TEXT, -- JSON array
                estimated_duration_minutes INTEGER,
                actual_duration_minutes INTEGER,
                dependencies TEXT, -- JSON array
                markdown_reference TEXT,
                FOREIGN KEY (parent_task_id) REFERENCES tasks(task_id)
            )
            """
        )

    async def _create_execution_records_table(self, conn) -> None:
        """
        Create execution_records table for tracking task execution steps.

        Issue #620.
        """
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_records (
                record_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                agent_context TEXT, -- JSON object
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            )
            """
        )

    async def _create_memory_entries_table(self, conn) -> None:
        """
        Create memory_entries table for general storage.

        Issue #620.
        """
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                metadata TEXT, -- JSON object
                timestamp REAL NOT NULL,
                embedding BLOB,
                reference_path TEXT,
                UNIQUE(category, content_hash)
            )
            """
        )

    async def _create_tables(self, conn) -> None:
        """
        Create database tables for tasks, execution records, and memory entries.

        Issue #281: Extracted helper for table creation.
        Issue #620: Further refactored to use individual table creation helpers.
        """
        await self._create_tasks_table(conn)
        await self._create_execution_records_table(conn)
        await self._create_memory_entries_table(conn)

    async def _create_indexes(self, conn) -> None:
        """
        Create performance indexes for all tables.

        Issue #281: Extracted helper for index creation.
        """
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_updated ON tasks(updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(assigned_agent)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id)",
            (
                "CREATE INDEX IF NOT EXISTS idx_execution_task "
                "ON execution_records(task_id)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS idx_execution_timestamp "
                "ON execution_records(timestamp)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS idx_execution_success "
                "ON execution_records(success)"
            ),
            "CREATE INDEX IF NOT EXISTS idx_memory_category ON memory_entries(category)",
            "CREATE INDEX IF NOT EXISTS idx_memory_timestamp ON memory_entries(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_memory_hash ON memory_entries(content_hash)",
        ]

        for index_query in indexes:
            await conn.execute(index_query)

    async def _init_database(self):
        """
        Initialize async database schema.

        Issue #281: Refactored from 113 lines to use extracted helper methods.
        """
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            try:
                async with aiosqlite.connect(self.db_path) as conn:
                    # Issue #281: uses helpers
                    await self._configure_pragmas(conn)
                    await self._create_tables(conn)
                    await self._create_indexes(conn)
                    await conn.commit()

                self._initialized = True
                logger.info("Async enhanced memory database initialized")
            except aiosqlite.Error as e:
                logger.error("Failed to initialize database: %s", e)
                raise RuntimeError(f"Database initialization failed: {e}")

    async def create_task(self, task: TaskEntry) -> str:
        """Create a new task with async performance (Issue #372 - uses model methods)."""
        await self._init_database()

        # Generate task ID if not provided using model method
        if not hasattr(task, "task_id") or not task.task_id:
            task.task_id = task.generate_task_id()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO tasks
                    (task_id, description, status, priority, created_at, updated_at,
                     completed_at, assigned_agent, parent_task_id, tags, metadata,
                     execution_log, estimated_duration_minutes, actual_duration_minutes,
                     dependencies, markdown_reference)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    task.to_db_tuple(),  # Issue #372: Use model method
                )
                await conn.commit()

            logger.info("Created task: %s", task.task_id)
            return task.task_id
        except aiosqlite.Error as e:
            logger.error("Failed to create task %s: %s", task.task_id, e)
            raise RuntimeError(f"Failed to create task: {e}")

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update task status with async performance"""
        await self._init_database()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                updates = {
                    "status": status.value,
                    "updated_at": datetime.now().timestamp(),
                }

                if status in TERMINAL_TASK_STATUSES:
                    updates["completed_at"] = datetime.now().timestamp()

                if metadata:
                    # Get existing metadata and merge
                    cursor = await conn.execute(
                        "SELECT metadata FROM tasks WHERE task_id = ?", (task_id,)
                    )
                    row = await cursor.fetchone()
                    if row:
                        existing_metadata = json.loads(row[0] or "{}")
                        existing_metadata.update(metadata)
                        updates["metadata"] = json.dumps(existing_metadata)

                # Build dynamic update query
                set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
                values = list(updates.values()) + [task_id]

                cursor = await conn.execute(
                    f"UPDATE tasks SET {set_clause} WHERE task_id = ?",  # nosec B608
                    values,
                )

                success = cursor.rowcount > 0
                await conn.commit()

            if success:
                logger.info("Updated task %s status to %s", task_id, status.value)
            else:
                logger.warning("Task %s not found for status update", task_id)

            return success
        except aiosqlite.Error as e:
            logger.error("Failed to update task %s status: %s", task_id, e)
            raise RuntimeError(f"Failed to update task status: {e}")

    async def log_execution(self, record: ExecutionRecord) -> str:
        """Log execution record with async performance"""
        await self._init_database()

        if not record.record_id:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            hash_input = f"{record.task_id}_{record.action}".encode()
            record_hash = hashlib.md5(hash_input, usedforsecurity=False).hexdigest()[:8]
            record.record_id = f"exec_{timestamp}_{record_hash}"

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    """
                    INSERT INTO execution_records
                    (record_id, task_id, timestamp, action, result, duration_ms,
                     success, error_message, agent_context)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.record_id,
                        record.task_id,
                        record.timestamp.timestamp(),
                        record.action,
                        record.result,
                        record.duration_ms,
                        record.success,
                        record.error_message,
                        json.dumps(record.agent_context),
                    ),
                )
                await conn.commit()

            logger.debug("Logged execution record: %s", record.record_id)
            return record.record_id
        except aiosqlite.Error as e:
            logger.error("Failed to log execution record: %s", e)
            raise RuntimeError(f"Failed to log execution: {e}")

    async def get_task(self, task_id: str) -> Optional[TaskEntry]:
        """Retrieve task by ID with async performance"""
        await self._init_database()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
                )
                row = await cursor.fetchone()

                if not row:
                    return None

                return TaskEntry(
                    task_id=row[0],
                    description=row[1],
                    status=TaskStatus(row[2]),
                    priority=Priority(row[3]),
                    created_at=datetime.fromtimestamp(row[4]),
                    updated_at=datetime.fromtimestamp(row[5]),
                    completed_at=datetime.fromtimestamp(row[6]) if row[6] else None,
                    assigned_agent=row[7],
                    parent_task_id=row[8],
                    tags=json.loads(row[9] or "[]"),
                    metadata=json.loads(row[10] or "{}"),
                    execution_log=json.loads(row[11] or "[]"),
                    estimated_duration_minutes=row[12],
                    actual_duration_minutes=row[13],
                    dependencies=json.loads(row[14] or "[]"),
                    markdown_reference=row[15],
                )
        except aiosqlite.Error as e:
            logger.error("Failed to get task %s: %s", task_id, e)
            raise RuntimeError(f"Failed to get task: {e}")

    async def get_tasks_by_status(
        self, status: TaskStatus, limit: int = 100, offset: int = 0
    ) -> List[TaskEntry]:
        """Get tasks by status with async performance"""
        await self._init_database()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT * FROM tasks WHERE status = ? "
                    "ORDER BY priority DESC, created_at DESC LIMIT ? OFFSET ?",
                    (status.value, limit, offset),
                )
                rows = await cursor.fetchall()

                tasks = []
                for row in rows:
                    tasks.append(
                        TaskEntry(
                            task_id=row[0],
                            description=row[1],
                            status=TaskStatus(row[2]),
                            priority=Priority(row[3]),
                            created_at=datetime.fromtimestamp(row[4]),
                            updated_at=datetime.fromtimestamp(row[5]),
                            completed_at=datetime.fromtimestamp(row[6])
                            if row[6]
                            else None,
                            assigned_agent=row[7],
                            parent_task_id=row[8],
                            tags=json.loads(row[9] or "[]"),
                            metadata=json.loads(row[10] or "{}"),
                            execution_log=json.loads(row[11] or "[]"),
                            estimated_duration_minutes=row[12],
                            actual_duration_minutes=row[13],
                            dependencies=json.loads(row[14] or "[]"),
                            markdown_reference=row[15],
                        )
                    )

                return tasks
        except aiosqlite.Error as e:
            logger.error("Failed to get tasks by status: %s", e)
            raise RuntimeError(f"Failed to get tasks: {e}")

    async def get_execution_history(
        self, task_id: str, limit: int = 100
    ) -> List[ExecutionRecord]:
        """Get execution history for a task with async performance"""
        await self._init_database()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT * FROM execution_records WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (task_id, limit),
                )
                rows = await cursor.fetchall()

                records = []
                for row in rows:
                    records.append(
                        ExecutionRecord(
                            record_id=row[0],
                            task_id=row[1],
                            timestamp=datetime.fromtimestamp(row[2]),
                            action=row[3],
                            result=row[4],
                            duration_ms=row[5],
                            success=bool(row[6]),
                            error_message=row[7],
                            agent_context=json.loads(row[8] or "{}"),
                        )
                    )

                return records
        except aiosqlite.Error as e:
            logger.error("Failed to get execution history for %s: %s", task_id, e)
            raise RuntimeError(f"Failed to get execution history: {e}")

    async def store_memory(
        self,
        category: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[bytes] = None,
        reference_path: Optional[str] = None,
    ) -> int:
        """Store memory entry with async performance"""
        await self._init_database()

        content_hash = hashlib.sha256(content.encode()).hexdigest()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    """
                    INSERT OR REPLACE INTO memory_entries
                    (category, content, content_hash, metadata, timestamp, embedding, reference_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        category,
                        content,
                        content_hash,
                        json.dumps(metadata or {}),
                        datetime.now().timestamp(),
                        embedding,
                        reference_path,
                    ),
                )
                memory_id = cursor.lastrowid
                await conn.commit()

            logger.debug("Stored memory entry %s in category %s", memory_id, category)
            return memory_id
        except aiosqlite.Error as e:
            logger.error("Failed to store memory entry: %s", e)
            raise RuntimeError(f"Failed to store memory: {e}")

    async def _gather_task_counts(self, conn) -> Dict[str, Any]:
        """Gather task counts by status and priority. Issue #620."""
        counts = {}
        cursor = await conn.execute(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status"
        )
        counts["tasks_by_status"] = dict(await cursor.fetchall())

        cursor = await conn.execute(
            "SELECT priority, COUNT(*) FROM tasks GROUP BY priority"
        )
        counts["tasks_by_priority"] = dict(await cursor.fetchall())
        return counts

    async def _gather_execution_metrics(self, conn) -> Dict[str, Any]:
        """Gather execution time and success rate metrics. Issue #620."""
        metrics = {}
        cursor = await conn.execute(
            "SELECT AVG(duration_ms) FROM execution_records WHERE success = 1"
        )
        result = await cursor.fetchone()
        metrics["avg_execution_time_ms"] = result[0] if result[0] else 0

        cursor = await conn.execute(
            "SELECT success, COUNT(*) FROM execution_records GROUP BY success"
        )
        success_data = dict(await cursor.fetchall())
        total_executions = sum(success_data.values())
        if total_executions > 0:
            metrics["success_rate"] = success_data.get(1, 0) / total_executions
        else:
            metrics["success_rate"] = 0
        return metrics

    async def _gather_recent_activity(self, conn) -> Dict[str, Any]:
        """Gather recent activity counts (last 24 hours). Issue #620."""
        recent_timestamp = (datetime.now() - timedelta(hours=24)).timestamp()
        activity = {}

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_at > ?",
            (recent_timestamp,),
        )
        activity["recent_tasks"] = (await cursor.fetchone())[0]

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM execution_records WHERE timestamp > ?",
            (recent_timestamp,),
        )
        activity["recent_executions"] = (await cursor.fetchone())[0]
        return activity

    async def get_task_statistics(self) -> Dict[str, Any]:
        """Get comprehensive task statistics with async performance."""
        await self._init_database()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                stats = {}
                stats.update(await self._gather_task_counts(conn))
                stats.update(await self._gather_execution_metrics(conn))
                stats.update(await self._gather_recent_activity(conn))
                return stats
        except aiosqlite.Error as e:
            logger.error("Failed to get task statistics: %s", e)
            raise RuntimeError(f"Failed to get task statistics: {e}")

    async def cleanup_old_data(self, retention_days: int = 90):
        """Clean up old data with async performance"""
        await self._init_database()

        cutoff_timestamp = (datetime.now() - timedelta(days=retention_days)).timestamp()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                # Clean up old execution records
                cursor = await conn.execute(
                    "DELETE FROM execution_records WHERE timestamp < ?",
                    (cutoff_timestamp,),
                )
                deleted_executions = cursor.rowcount

                # Clean up old completed tasks (keep failed ones for analysis)
                cursor = await conn.execute(
                    "DELETE FROM tasks WHERE status = 'completed' AND completed_at < ?",
                    (cutoff_timestamp,),
                )
                deleted_tasks = cursor.rowcount

                # Clean up old memory entries
                cursor = await conn.execute(
                    "DELETE FROM memory_entries WHERE timestamp < ?",
                    (cutoff_timestamp,),
                )
                deleted_memories = cursor.rowcount

                await conn.commit()

                logger.info(
                    f"Cleanup completed: {deleted_executions} executions, "
                    f"{deleted_tasks} tasks, {deleted_memories} memories"
                )
        except aiosqlite.Error as e:
            logger.error("Failed to cleanup old data: %s", e)
            raise RuntimeError(f"Failed to cleanup old data: {e}")

    async def close(self):
        """Close the async enhanced memory manager"""
        logger.info("Async enhanced memory manager closed")


# Global async enhanced memory manager instance (thread-safe)
import threading

_async_enhanced_memory_manager = None
_async_enhanced_memory_manager_lock = threading.Lock()


def get_async_enhanced_memory_manager() -> AsyncEnhancedMemoryManager:
    """Get global async enhanced memory manager instance (thread-safe)"""
    global _async_enhanced_memory_manager
    if _async_enhanced_memory_manager is None:
        with _async_enhanced_memory_manager_lock:
            # Double-check after acquiring lock
            if _async_enhanced_memory_manager is None:
                _async_enhanced_memory_manager = AsyncEnhancedMemoryManager()
    return _async_enhanced_memory_manager
