# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task Storage Implementation - Task execution history management
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import aiosqlite

from ..enums import TaskPriority, TaskStatus
from ..models import TaskExecutionRecord

logger = logging.getLogger(__name__)

# Field categories for update_task (Issue #315: extracted to reduce nesting)
_ENUM_FIELDS = {"status": TaskStatus, "priority": TaskPriority}
_JSON_FIELDS = {"inputs", "outputs", "metadata", "markdown_references", "subtask_ids"}
_DIRECT_FIELDS = {
    "started_at",
    "completed_at",
    "duration_seconds",
    "retry_count",
    "error_message",
    "agent_type",
}


def _process_update_field(key: str, value: Any) -> tuple[Optional[str], Optional[Any]]:
    """Process a single update field into SQL clause and value (Issue #315: extracted).

    Args:
        key: Field name
        value: Field value

    Returns:
        Tuple of (set_clause, processed_value) or (None, None) if field not recognized
    """
    # Handle enum fields
    if key in _ENUM_FIELDS:
        expected_type = _ENUM_FIELDS[key]
        if isinstance(value, expected_type):
            return f"{key} = ?", value.value
        return None, None

    # Handle JSON fields
    if key in _JSON_FIELDS:
        return f"{key}_json = ?", json.dumps(value) if value else None

    # Handle direct fields
    if key in _DIRECT_FIELDS:
        return f"{key} = ?", value

    return None, None


class TaskStorage:
    """
    Task-specific storage implementation (ITaskStorage)

    Responsibility: Manage task execution history in SQLite database
    """

    def __init__(self, db_path: Union[str, Path]):
        """Initialize task storage with SQLite database path."""
        self.db_path = Path(db_path) if isinstance(db_path, str) else db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self):
        """Get database connection context manager"""
        return aiosqlite.connect(self.db_path)

    async def initialize(self):
        """Initialize task execution history table"""
        try:
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
        except aiosqlite.Error as e:
            logger.error("Failed to initialize task storage: %s", e)
            raise RuntimeError(f"Task storage initialization failed: {e}")

    async def log_task(self, record: TaskExecutionRecord) -> str:
        """Log task execution record (Issue #372 - uses model method)."""
        try:
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
                    record.to_db_tuple(),  # Issue #372: Use model method
                )
                await conn.commit()

            logger.debug("Logged task: %s (%s)", record.task_id, record.status.value)
            return record.task_id
        except aiosqlite.Error as e:
            logger.error("Failed to log task %s: %s", record.task_id, e)
            raise RuntimeError(f"Failed to log task: {e}")

    async def update_task(self, task_id: str, **updates) -> bool:
        """Update task fields dynamically.

        Issue #315: Refactored to use helper function for reduced nesting.
        """
        if not updates:
            return False

        # Build dynamic UPDATE query using helper
        set_clauses = []
        values = []

        for key, value in updates.items():
            clause, processed_value = _process_update_field(key, value)
            if clause:
                set_clauses.append(clause)
                values.append(processed_value)

        if not set_clauses:
            return False

        query = f"UPDATE task_execution_history SET {', '.join(set_clauses)} WHERE task_id = ?"
        values.append(task_id)

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(query, values)
                await conn.commit()
                return cursor.rowcount > 0
        except aiosqlite.Error as e:
            logger.error("Failed to update task %s: %s", task_id, e)
            raise RuntimeError(f"Failed to update task: {e}")

    async def get_task(self, task_id: str) -> Optional[TaskExecutionRecord]:
        """Retrieve single task by ID"""
        try:
            async with self._get_connection() as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(
                    "SELECT * FROM task_execution_history WHERE task_id = ?", (task_id,)
                )
                row = await cursor.fetchone()

                if not row:
                    return None

                return self._row_to_record(row)
        except aiosqlite.Error as e:
            logger.error("Failed to get task %s: %s", task_id, e)
            raise RuntimeError(f"Failed to get task: {e}")

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

        try:
            async with self._get_connection() as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, values)
                rows = await cursor.fetchall()
                return [self._row_to_record(row) for row in rows]
        except aiosqlite.Error as e:
            logger.error("Failed to get task history: %s", e)
            raise RuntimeError(f"Failed to get task history: {e}")

    async def get_stats(self) -> Dict[str, Any]:
        """Get task storage statistics"""
        try:
            async with self._get_connection() as conn:
                conn.row_factory = aiosqlite.Row
                # Total tasks
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM task_execution_history"
                )
                total = (await cursor.fetchone())[0]

                # Tasks by status
                cursor = await conn.execute(
                    """
                    SELECT status, COUNT(*)
                    FROM task_execution_history
                    GROUP BY status
                """
                )
                by_status = {row[0]: row[1] for row in await cursor.fetchall()}

                # Tasks by priority
                cursor = await conn.execute(
                    """
                    SELECT priority, COUNT(*)
                    FROM task_execution_history
                    GROUP BY priority
                """
                )
                by_priority = {row[0]: row[1] for row in await cursor.fetchall()}

                return {
                    "total_tasks": total,
                    "by_status": by_status,
                    "by_priority": by_priority,
                }
        except aiosqlite.Error as e:
            logger.error("Failed to get task stats: %s", e)
            raise RuntimeError(f"Failed to get task stats: {e}")

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


__all__ = ["TaskStorage"]
