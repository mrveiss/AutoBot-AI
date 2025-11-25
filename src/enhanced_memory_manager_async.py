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

from src.constants.network_constants import NetworkConstants

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
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}
        if self.execution_log is None:
            self.execution_log = []
        if self.dependencies is None:
            self.dependencies = []


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
        if self.agent_context is None:
            self.agent_context = {}


class AsyncEnhancedMemoryManager:
    """Async enhanced memory manager with comprehensive task tracking"""

    def __init__(self, db_path: str = "data/enhanced_memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize async database setup
        self._initialized = False
        self._init_lock = asyncio.Lock()

        logger.info(f"Async Enhanced Memory Manager initialized: {self.db_path}")

    async def _init_database(self):
        """Initialize async database schema"""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            async with aiosqlite.connect(self.db_path) as conn:
                # Enable WAL mode for better concurrency
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA cache_size=10000")
                await conn.execute("PRAGMA temp_store=MEMORY")
                await conn.execute("PRAGMA foreign_keys=ON")

                # Tasks table with enhanced schema
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

                # Execution records table
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

                # Memory entries table for general storage
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

                # Performance indexes
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

                await conn.commit()

            self._initialized = True
            logger.info("Async enhanced memory database initialized")

    async def create_task(self, task: TaskEntry) -> str:
        """Create a new task with async performance"""
        await self._init_database()

        # Generate task ID if not provided
        if not hasattr(task, "task_id") or not task.task_id:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            desc_hash = hashlib.md5(task.description.encode()).hexdigest()[:8]
            task.task_id = f"task_{timestamp}_{desc_hash}"

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
                (
                    task.task_id,
                    task.description,
                    task.status.value,
                    task.priority.value,
                    task.created_at.timestamp(),
                    task.updated_at.timestamp(),
                    task.completed_at.timestamp() if task.completed_at else None,
                    task.assigned_agent,
                    task.parent_task_id,
                    json.dumps(task.tags),
                    json.dumps(task.metadata),
                    json.dumps(task.execution_log),
                    task.estimated_duration_minutes,
                    task.actual_duration_minutes,
                    json.dumps(task.dependencies),
                    task.markdown_reference,
                ),
            )
            await conn.commit()

        logger.info(f"Created task: {task.task_id}")
        return task.task_id

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update task status with async performance"""
        await self._init_database()

        async with aiosqlite.connect(self.db_path) as conn:
            updates = {
                "status": status.value,
                "updated_at": datetime.now().timestamp(),
            }

            if status in [
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            ]:
                updates["completed_at"] = datetime.now().timestamp()

            if metadata:
                # Get existing metadata and merge
                cursor = await conn.execute(
                    "SELECT metadata FROM tasks WHERE task_id = ?", (task_id,)
                ),
                row = await cursor.fetchone()
                if row:
                    existing_metadata = json.loads(row[0] or "{}")
                    existing_metadata.update(metadata)
                    updates["metadata"] = json.dumps(existing_metadata)

            # Build dynamic update query
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [task_id]

            cursor = await conn.execute(
                f"UPDATE tasks SET {set_clause} WHERE task_id = ?", values
            )

            success = cursor.rowcount > 0
            await conn.commit()

        if success:
            logger.info(f"Updated task {task_id} status to {status.value}")
        else:
            logger.warning(f"Task {task_id} not found for status update")

        return success

    async def log_execution(self, record: ExecutionRecord) -> str:
        """Log execution record with async performance"""
        await self._init_database()

        if not record.record_id:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            hash_input = f'{record.task_id}_{record.action}'.encode()
            record_hash = hashlib.md5(hash_input).hexdigest()[:8]
            record.record_id = f"exec_{timestamp}_{record_hash}"

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

        logger.debug(f"Logged execution record: {record.record_id}")
        return record.record_id

    async def get_task(self, task_id: str) -> Optional[TaskEntry]:
        """Retrieve task by ID with async performance"""
        await self._init_database()

        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ),
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

    async def get_tasks_by_status(
        self, status: TaskStatus, limit: int = 100, offset: int = 0
    ) -> List[TaskEntry]:
        """Get tasks by status with async performance"""
        await self._init_database()

        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM tasks WHERE status = ? "
                "ORDER BY priority DESC, created_at DESC LIMIT ? OFFSET ?",
                (status.value, limit, offset),
            ),
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
                )

            return tasks

    async def get_execution_history(
        self, task_id: str, limit: int = 100
    ) -> List[ExecutionRecord]:
        """Get execution history for a task with async performance"""
        await self._init_database()

        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM execution_records WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?",
                (task_id, limit),
            ),
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
            ),
            memory_id = cursor.lastrowid
            await conn.commit()

        logger.debug(f"Stored memory entry {memory_id} in category {category}")
        return memory_id

    async def get_task_statistics(self) -> Dict[str, Any]:
        """Get comprehensive task statistics with async performance"""
        await self._init_database()

        async with aiosqlite.connect(self.db_path) as conn:
            stats = {}

            # Task counts by status
            cursor = await conn.execute(
                "SELECT status, COUNT(*) FROM tasks GROUP BY status"
            )
            stats["tasks_by_status"] = dict(await cursor.fetchall())

            # Task counts by priority
            cursor = await conn.execute(
                "SELECT priority, COUNT(*) FROM tasks GROUP BY priority"
            )
            stats["tasks_by_priority"] = dict(await cursor.fetchall())

            # Average execution time
            cursor = await conn.execute(
                "SELECT AVG(duration_ms) FROM execution_records WHERE success = 1"
            ),
            result = await cursor.fetchone()
            stats["avg_execution_time_ms"] = result[0] if result[0] else 0

            # Success rate
            cursor = await conn.execute(
                "SELECT success, COUNT(*) FROM execution_records GROUP BY success"
            ),
            success_data = dict(await cursor.fetchall())
            total_executions = sum(success_data.values())
            if total_executions > 0:
                stats["success_rate"] = success_data.get(1, 0) / total_executions
            else:
                stats["success_rate"] = 0

            # Recent activity (last 24 hours)
            recent_timestamp = (datetime.now() - timedelta(hours=24)).timestamp()
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE created_at > ?", (recent_timestamp,)
            )
            stats["recent_tasks"] = (await cursor.fetchone())[0]

            cursor = await conn.execute(
                "SELECT COUNT(*) FROM execution_records WHERE timestamp > ?",
                (recent_timestamp,),
            )
            stats["recent_executions"] = (await cursor.fetchone())[0]

            return stats

    async def cleanup_old_data(self, retention_days: int = 90):
        """Clean up old data with async performance"""
        await self._init_database()

        cutoff_timestamp = (datetime.now() - timedelta(days=retention_days)).timestamp()

        async with aiosqlite.connect(self.db_path) as conn:
            # Clean up old execution records
            cursor = await conn.execute(
                "DELETE FROM execution_records WHERE timestamp < ?", (cutoff_timestamp,)
            ),
            deleted_executions = cursor.rowcount

            # Clean up old completed tasks (keep failed ones for analysis)
            cursor = await conn.execute(
                "DELETE FROM tasks WHERE status = 'completed' AND completed_at < ?",
                (cutoff_timestamp,),
            ),
            deleted_tasks = cursor.rowcount

            # Clean up old memory entries
            cursor = await conn.execute(
                "DELETE FROM memory_entries WHERE timestamp < ?", (cutoff_timestamp,)
            ),
            deleted_memories = cursor.rowcount

            await conn.commit()

            logger.info(
                f"Cleanup completed: {deleted_executions} executions, "
                f"{deleted_tasks} tasks, {deleted_memories} memories"
            )

    async def close(self):
        """Close the async enhanced memory manager"""
        logger.info("Async enhanced memory manager closed")


# Global async enhanced memory manager instance
_async_enhanced_memory_manager = None


def get_async_enhanced_memory_manager() -> AsyncEnhancedMemoryManager:
    """Get global async enhanced memory manager instance"""
    global _async_enhanced_memory_manager
    if _async_enhanced_memory_manager is None:
        _async_enhanced_memory_manager = AsyncEnhancedMemoryManager()
    return _async_enhanced_memory_manager
