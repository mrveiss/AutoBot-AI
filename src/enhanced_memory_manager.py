# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Memory Manager for AutoBot Phase 7
Comprehensive task logging and execution history with SQLite and markdown references
"""

import base64
import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.database_pool import get_connection_pool

logger = logging.getLogger(__name__)


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


@dataclass
class TaskExecutionRecord:
    """Comprehensive task execution record"""

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


class EnhancedMemoryManager:
    """
    Enhanced Memory Manager with SQLite backend for comprehensive task logging
    and execution history tracking with markdown reference system
    """

    def __init__(self, db_path: str = "data/enhanced_memory.db"):
        """Initialize enhanced memory manager with SQLite database path."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        logger.info(
            f"Enhanced Memory Manager initialized with database: {self.db_path}"
        )

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """Create all database tables (Issue #665: extracted helper).

        Args:
            conn: SQLite connection
        """
        conn.execute(
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
                parent_task_id TEXT,
                metadata_json TEXT,
                FOREIGN KEY (parent_task_id) REFERENCES task_execution_history(task_id)
            )
        """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS markdown_references (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                markdown_file_path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                reference_type TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (task_id) REFERENCES task_execution_history(task_id)
            )
        """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embedding_cache (
                content_hash TEXT PRIMARY KEY,
                content_type TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_data BLOB NOT NULL,
                created_at TIMESTAMP NOT NULL,
                last_accessed TIMESTAMP NOT NULL
            )
        """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subtask_relationships (
                parent_task_id TEXT NOT NULL,
                subtask_id TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                PRIMARY KEY (parent_task_id, subtask_id),
                FOREIGN KEY (parent_task_id) REFERENCES task_execution_history(task_id),
                FOREIGN KEY (subtask_id) REFERENCES task_execution_history(task_id)
            )
        """
        )

    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """Create performance indexes (Issue #665: extracted helper).

        Args:
            conn: SQLite connection
        """
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_task_status ON task_execution_history(status)
        """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_task_created_at ON task_execution_history(created_at)
        """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_task_agent_type ON task_execution_history(agent_type)
        """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_markdown_task_id ON markdown_references(task_id)
        """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_embedding_model ON embedding_cache(embedding_model)
        """
        )

    def _init_database(self):
        """Initialize SQLite database with comprehensive schema.

        Issue #665: Refactored to use _create_tables and _create_indexes helpers.
        """
        with sqlite3.connect(self.db_path) as conn:
            self._create_tables(conn)
            self._create_indexes(conn)
            conn.commit()

    def create_task_record(
        self,
        task_name: str,
        description: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        agent_type: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
        parent_task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new task execution record"""
        task_id = self._generate_task_id(task_name)
        created_at = datetime.now()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO task_execution_history
                (task_id, task_name, description, status, priority, created_at,
                 agent_type, inputs_json, parent_task_id, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    task_id,
                    task_name,
                    description,
                    TaskStatus.PENDING.value,
                    priority.value,
                    created_at,
                    agent_type,
                    json.dumps(inputs) if inputs else None,
                    parent_task_id,
                    json.dumps(metadata) if metadata else None,
                ),
            )

            # Add subtask relationship if this is a subtask
            if parent_task_id:
                conn.execute(
                    """
                    INSERT INTO subtask_relationships (parent_task_id, subtask_id, created_at)
                    VALUES (?, ?, ?)
                """,
                    (parent_task_id, task_id, created_at),
                )

            conn.commit()

        logger.info("Created task record: %s - %s", task_id, task_name)
        return task_id

    def start_task(self, task_id: str) -> bool:
        """Mark task as started"""
        started_at = datetime.now()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE task_execution_history
                SET status = ?, started_at = ?
                WHERE task_id = ?
            """,
                (TaskStatus.IN_PROGRESS.value, started_at, task_id),
            )

            if cursor.rowcount > 0:
                conn.commit()
                logger.info("Started task: %s", task_id)
                return True
            else:
                logger.warning("Task not found for start: %s", task_id)
                return False

    def complete_task(
        self,
        task_id: str,
        outputs: Optional[Dict[str, Any]] = None,
        status: TaskStatus = TaskStatus.COMPLETED,
    ) -> bool:
        """Mark task as completed with optional outputs"""
        completed_at = datetime.now()

        with sqlite3.connect(self.db_path) as conn:
            # Get task start time to calculate duration
            cursor = conn.execute(
                """
                SELECT started_at FROM task_execution_history WHERE task_id = ?
            """,
                (task_id,),
            )

            row = cursor.fetchone()
            if not row:
                logger.warning("Task not found for completion: %s", task_id)
                return False

            started_at = row[0]
            duration = None
            if started_at:
                started_dt = datetime.fromisoformat(started_at)
                duration = (completed_at - started_dt).total_seconds()

            cursor = conn.execute(
                """
                UPDATE task_execution_history
                SET status = ?, completed_at = ?, duration_seconds = ?, outputs_json = ?
                WHERE task_id = ?
            """,
                (
                    status.value,
                    completed_at,
                    duration,
                    json.dumps(outputs) if outputs else None,
                    task_id,
                ),
            )

            if cursor.rowcount > 0:
                conn.commit()
                logger.info("Completed task: %s (duration: %ss)", task_id, duration)
                return True
            else:
                return False

    def fail_task(self, task_id: str, error_message: str, retry_count: int = 0) -> bool:
        """Mark task as failed with error information"""
        completed_at = datetime.now()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE task_execution_history
                SET status = ?, completed_at = ?, error_message = ?, retry_count = ?
                WHERE task_id = ?
            """,
                (
                    TaskStatus.FAILED.value,
                    completed_at,
                    error_message,
                    retry_count,
                    task_id,
                ),
            )

            if cursor.rowcount > 0:
                conn.commit()
                logger.error("Failed task: %s - %s", task_id, error_message)
                return True
            else:
                return False

    def add_markdown_reference(
        self,
        task_id: str,
        markdown_file_path: str,
        reference_type: str = "documentation",
    ) -> bool:
        """Add markdown file reference to task"""
        if not Path(markdown_file_path).exists():
            logger.warning("Markdown file not found: %s", markdown_file_path)
            return False

        # Calculate content hash for tracking changes
        with open(markdown_file_path, "r", encoding="utf-8") as f:
            content = f.read()
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO markdown_references
                (task_id, markdown_file_path, content_hash, reference_type, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    task_id,
                    markdown_file_path,
                    content_hash,
                    reference_type,
                    datetime.now(),
                ),
            )

            conn.commit()

        logger.info("Added markdown reference: %s -> %s", task_id, markdown_file_path)
        return True

    def store_embedding(
        self,
        content: str,
        content_type: str,
        embedding_model: str,
        embedding_vector: List[float],
    ) -> bool:
        """Store embedding vector as pickled blob in SQLite"""
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Serialize embedding vector using JSON and base64 encode
        # This is safer than pickle for security
        import json

        embedding_data = base64.b64encode(json.dumps(embedding_vector).encode())

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO embedding_cache
                (content_hash, content_type, embedding_model, embedding_data,
                 created_at, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    content_hash,
                    content_type,
                    embedding_model,
                    embedding_data,
                    datetime.now(),
                    datetime.now(),
                ),
            )

            conn.commit()

        logger.debug("Stored embedding for content hash: %s...", content_hash[:16])
        return True

    def get_embedding(
        self, content: str, embedding_model: str
    ) -> Optional[List[float]]:
        """Retrieve cached embedding vector"""
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT embedding_data FROM embedding_cache
                WHERE content_hash = ? AND embedding_model = ?
            """,
                (content_hash, embedding_model),
            )

            row = cursor.fetchone()
            if row:
                # Update last accessed time
                conn.execute(
                    """
                    UPDATE embedding_cache SET last_accessed = ?
                    WHERE content_hash = ? AND embedding_model = ?
                """,
                    (datetime.now(), content_hash, embedding_model),
                )
                conn.commit()

                # Deserialize embedding vector using JSON (safer than pickle)
                import json

                embedding_data = base64.b64decode(row[0])
                embedding_vector = json.loads(embedding_data.decode())

                logger.debug("Retrieved cached embedding for: %s...", content_hash[:16])
                return embedding_vector

        return None

    def _batch_load_markdown_refs(
        self, conn: sqlite3.Connection, task_ids: List[str]
    ) -> Dict[str, List[str]]:
        """
        Batch load markdown references for multiple tasks.

        Issue #665: Extracted from get_task_history to reduce function length.

        Args:
            conn: SQLite connection
            task_ids: List of task IDs to load references for

        Returns:
            Dict mapping task_id to list of markdown file paths
        """
        task_ids_placeholder = ",".join(["?" for _ in task_ids])
        ref_cursor = conn.execute(
            f"""
            SELECT task_id, markdown_file_path
            FROM markdown_references
            WHERE task_id IN ({task_ids_placeholder})
            """,
            task_ids,
        )
        markdown_refs_by_task: Dict[str, List[str]] = {}
        for ref_row in ref_cursor.fetchall():
            task_id = ref_row[0]
            if task_id not in markdown_refs_by_task:
                markdown_refs_by_task[task_id] = []
            markdown_refs_by_task[task_id].append(ref_row[1])
        return markdown_refs_by_task

    def _batch_load_subtasks(
        self, conn: sqlite3.Connection, task_ids: List[str]
    ) -> Dict[str, List[str]]:
        """
        Batch load subtask relationships for multiple tasks.

        Issue #665: Extracted from get_task_history to reduce function length.

        Args:
            conn: SQLite connection
            task_ids: List of parent task IDs to load subtasks for

        Returns:
            Dict mapping parent_task_id to list of subtask IDs
        """
        task_ids_placeholder = ",".join(["?" for _ in task_ids])
        subtask_cursor = conn.execute(
            f"""
            SELECT parent_task_id, subtask_id
            FROM subtask_relationships
            WHERE parent_task_id IN ({task_ids_placeholder})
            """,
            task_ids,
        )
        subtasks_by_parent: Dict[str, List[str]] = {}
        for subtask_row in subtask_cursor.fetchall():
            parent_id = subtask_row[0]
            if parent_id not in subtasks_by_parent:
                subtasks_by_parent[parent_id] = []
            subtasks_by_parent[parent_id].append(subtask_row[1])
        return subtasks_by_parent

    def _build_task_record(
        self,
        row: tuple,
        markdown_refs: List[str],
        subtask_ids: List[str],
    ) -> TaskExecutionRecord:
        """
        Build a TaskExecutionRecord from a database row and related data.

        Issue #281: Extracted from get_task_history to reduce function length
        and improve readability.

        Args:
            row: Database row tuple with task fields
            markdown_refs: List of markdown file paths for this task
            subtask_ids: List of subtask IDs for this task

        Returns:
            TaskExecutionRecord instance
        """
        return TaskExecutionRecord(
            task_id=row[0],
            task_name=row[1],
            description=row[2],
            status=TaskStatus(row[3]),
            priority=TaskPriority(row[4]),
            created_at=datetime.fromisoformat(row[5]),
            started_at=datetime.fromisoformat(row[6]) if row[6] else None,
            completed_at=datetime.fromisoformat(row[7]) if row[7] else None,
            duration_seconds=row[8],
            agent_type=row[9],
            inputs=json.loads(row[10]) if row[10] else None,
            outputs=json.loads(row[11]) if row[11] else None,
            error_message=row[12],
            retry_count=row[13],
            parent_task_id=row[14],
            markdown_references=markdown_refs,
            subtask_ids=subtask_ids,
            metadata=json.loads(row[15]) if row[15] else None,
        )

    def get_task_history(
        self,
        agent_type: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
        days_back: int = 30,
    ) -> List[TaskExecutionRecord]:
        """Get task execution history with optional filtering"""
        cutoff_date = datetime.now() - timedelta(days=days_back)

        query = """
            SELECT task_id, task_name, description, status, priority,
                   created_at, started_at, completed_at, duration_seconds,
                   agent_type, inputs_json, outputs_json, error_message,
                   retry_count, parent_task_id, metadata_json
            FROM task_execution_history
            WHERE created_at > ?
        """
        params = [cutoff_date]

        if agent_type:
            query += " AND agent_type = ?"
            params.append(agent_type)

        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        tasks: List[TaskExecutionRecord] = []
        # Use connection pool instead of direct connection
        pool = get_connection_pool(self.db_path)
        with pool.get_connection() as conn:
            cursor = conn.execute(query, params)
            task_rows = cursor.fetchall()

            if not task_rows:
                return tasks

            # Extract task IDs for batch queries
            task_ids = [row[0] for row in task_rows]

            # Issue #665: Use extracted helpers for batch loading
            markdown_refs_by_task = self._batch_load_markdown_refs(conn, task_ids)
            subtasks_by_parent = self._batch_load_subtasks(conn, task_ids)

            # Build task objects using extracted helper (Issue #281)
            for row in task_rows:
                task_id = row[0]
                markdown_refs = markdown_refs_by_task.get(task_id, [])
                subtask_ids = subtasks_by_parent.get(task_id, [])
                task = self._build_task_record(row, markdown_refs, subtask_ids)
                tasks.append(task)

        return tasks

    def get_task_statistics(self, days_back: int = 30) -> Dict[str, Any]:
        """Get comprehensive task execution statistics"""
        cutoff_date = datetime.now() - timedelta(days=days_back)

        with sqlite3.connect(self.db_path) as conn:
            # Overall statistics
            cursor = conn.execute(
                """
                SELECT status, COUNT(*)
                FROM task_execution_history
                WHERE created_at > ?
                GROUP BY status
            """,
                (cutoff_date,),
            )

            status_counts = {row[0]: row[1] for row in cursor.fetchall()}

            # Agent type statistics
            cursor = conn.execute(
                """
                SELECT agent_type, COUNT(*), AVG(duration_seconds)
                FROM task_execution_history
                WHERE created_at > ? AND agent_type IS NOT NULL
                GROUP BY agent_type
            """,
                (cutoff_date,),
            )

            agent_stats = {}
            for row in cursor.fetchall():
                agent_stats[row[0]] = {"count": row[1], "avg_duration": row[2]}

            # Success rate and performance metrics
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_tasks,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_tasks,
                    AVG(duration_seconds) as avg_duration,
                    AVG(retry_count) as avg_retries
                FROM task_execution_history
                WHERE created_at > ?
            """,
                (cutoff_date,),
            )

            row = cursor.fetchone()
            total_tasks = row[0] if row[0] else 0
            completed_tasks = row[1] if row[1] else 0
            success_rate = (
                (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            )

            return {
                "period_days": days_back,
                "total_tasks": total_tasks,
                "status_breakdown": status_counts,
                "success_rate_percent": round(success_rate, 2),
                "avg_duration_seconds": row[2],
                "avg_retry_count": row[3],
                "agent_statistics": agent_stats,
                "embedding_cache_size": self._get_embedding_cache_size(),
            }

    def cleanup_old_data(self, days_to_keep: int = 90):
        """Clean up old task records and embeddings"""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        with sqlite3.connect(self.db_path) as conn:
            # Clean up old task records
            cursor = conn.execute(
                """
                DELETE FROM task_execution_history
                WHERE created_at < ?
            """,
                (cutoff_date,),
            )
            tasks_deleted = cursor.rowcount

            # Clean up old embeddings (keep frequently accessed ones)
            cursor = conn.execute(
                """
                DELETE FROM embedding_cache
                WHERE last_accessed < ?
            """,
                (cutoff_date,),
            )
            embeddings_deleted = cursor.rowcount

            conn.commit()

        logger.info(
            f"Cleanup completed: {tasks_deleted} tasks, {embeddings_deleted} embeddings deleted"
        )
        return {
            "tasks_deleted": tasks_deleted,
            "embeddings_deleted": embeddings_deleted,
        }

    def _generate_task_id(self, task_name: str) -> str:
        """Generate unique task ID"""
        timestamp = datetime.now().isoformat()
        content = f"{task_name}_{timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_embedding_cache_size(self) -> int:
        """Get current embedding cache size"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM embedding_cache")
            return cursor.fetchone()[0]
