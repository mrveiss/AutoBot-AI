# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# src/memory_manager_async.py
"""
Async-enabled Long-Term Memory Manager for AutoBot Agent

This module provides async versions of database operations using aiosqlite
for improved performance and non-blocking database access.
"""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, FrozenSet, List, Optional

import aiosqlite


# Import the centralized ConfigManager
from src.config import UnifiedConfigManager

# Issue #380: Module-level frozensets for task status checks
_ACTIVE_STATUSES: FrozenSet[str] = frozenset({"IN_PROGRESS", "DONE", "FAILED"})
_COMPLETED_STATUSES: FrozenSet[str] = frozenset({"DONE", "FAILED"})

# Create singleton config instance
global_config_manager = UnifiedConfigManager()

# Import shared path utilities
from src.utils.common import PathUtils


@dataclass
class MemoryEntry:
    """Structured memory entry for consistent data handling"""

    id: Optional[int]
    category: str  # 'task', 'execution', 'state', 'config', 'fact', 'conversation'
    content: str
    metadata: Dict[str, Any]
    timestamp: datetime
    reference_path: Optional[str] = None  # Path to markdown files
    embedding: Optional[bytes] = None  # Pickled embedding vector


class AsyncLongTermMemoryManager:
    """
    Async version of long-term memory system using aiosqlite.
    Provides non-blocking database operations for better performance.
    """

    def __init__(self, config_path: Optional[str] = None):
        """Initialize async memory manager with config, database path, and retention settings."""
        # Use centralized configuration manager
        self.config = global_config_manager.to_dict()

        # Memory database path from centralized config
        memory_config = self.config.get("memory", {})
        data_config = self.config.get("data", {})
        default_db_path = (
            global_config_manager.get_path("data", "long_term_db")
            or "data/agent_memory.db"
        )
        self.db_path = PathUtils.resolve_path(
            memory_config.get("long_term_db_path")
            or data_config.get("long_term_db_path", default_db_path)
        )

        # Memory retention settings
        self.retention_days = memory_config.get("retention_days", 90)
        self.max_entries_per_category = memory_config.get(
            "max_entries_per_category", 10000
        )

        # Initialize async database setup
        self._initialized = False
        self._init_lock = asyncio.Lock()

        self.logger = logging.getLogger(__name__)
        logging.info(f"Async long-term memory manager initialized at {self.db_path}")

    async def _setup_db_pragmas(self, conn) -> None:
        """Configure database pragmas for optimal performance."""
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA cache_size=10000")
        await conn.execute("PRAGMA temp_store=MEMORY")
        await conn.execute("PRAGMA foreign_keys=ON")

    async def _create_memory_entries_table(self, conn) -> None:
        """Create main memory table for all types of long-term storage."""
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                reference_path TEXT,
                embedding BLOB,
                content_hash TEXT,
                UNIQUE(category, content_hash)
            )
        """)

    async def _create_task_logs_table(self, conn) -> None:
        """Create task execution logs table."""
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS task_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                description TEXT NOT NULL,
                result TEXT,
                execution_time_ms INTEGER,
                error_message TEXT,
                started_at DATETIME,
                completed_at DATETIME,
                metadata TEXT
            )
        """)

    async def _create_agent_states_table(self, conn) -> None:
        """Create agent state snapshots table."""
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state_name TEXT NOT NULL,
                state_data TEXT NOT NULL,
                phase INTEGER,
                active_tasks TEXT,
                system_status TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

    async def _create_conversation_history_table(self, conn) -> None:
        """Create conversation history table."""
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_id TEXT UNIQUE,
                response_time_ms INTEGER,
                token_usage INTEGER,
                model_used TEXT
            )
        """)

    async def _create_config_history_table(self, conn) -> None:
        """Create configuration changes table."""
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS config_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT NOT NULL,
                change_reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                rollback_available BOOLEAN DEFAULT TRUE
            )
        """)

    async def _create_indexes(self, conn) -> None:
        """Create performance indexes for all tables."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_memory_category ON memory_entries(category)",
            "CREATE INDEX IF NOT EXISTS idx_memory_timestamp ON memory_entries(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_memory_hash ON memory_entries(content_hash)",
            "CREATE INDEX IF NOT EXISTS idx_task_status ON task_logs(status)",
            "CREATE INDEX IF NOT EXISTS idx_task_type ON task_logs(task_type)",
            "CREATE INDEX IF NOT EXISTS idx_task_started ON task_logs(started_at)",
            "CREATE INDEX IF NOT EXISTS idx_agent_state_name ON agent_states(state_name)",
            "CREATE INDEX IF NOT EXISTS idx_agent_timestamp ON agent_states(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_conversation_session ON conversation_history(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_conversation_timestamp ON conversation_history(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_config_key ON config_history(config_key)",
            "CREATE INDEX IF NOT EXISTS idx_config_timestamp ON config_history(timestamp)",
        ]
        for index_query in indexes:
            await conn.execute(index_query)

    async def _init_memory_db(self):
        """
        Initialize async SQLite database with comprehensive memory tables.

        Issue #281: Refactored from 129 lines to use extracted helper methods.
        """
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

            try:
                async with aiosqlite.connect(self.db_path) as conn:
                    await self._setup_db_pragmas(conn)
                    await self._create_memory_entries_table(conn)
                    await self._create_task_logs_table(conn)
                    await self._create_agent_states_table(conn)
                    await self._create_conversation_history_table(conn)
                    await self._create_config_history_table(conn)
                    await self._create_indexes(conn)
                    await conn.commit()

                self._initialized = True
                self.logger.info("Async memory database initialization completed")
            except aiosqlite.Error as e:
                self.logger.error("Failed to initialize memory database: %s", e)
                raise RuntimeError(f"Failed to initialize memory database: {e}")

    async def store_memory(
        self,
        category: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        reference_path: Optional[str] = None,
        embedding: Optional[bytes] = None,
    ) -> int:
        """Store a memory entry with async performance"""
        await self._init_memory_db()

        # Generate content hash for duplicate detection
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    """
                    INSERT OR REPLACE INTO memory_entries
                    (category, content, metadata, timestamp, reference_path, embedding, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        category,
                        content,
                        json.dumps(metadata or {}),
                        datetime.now().timestamp(),
                        reference_path,
                        embedding,
                        content_hash,
                    ),
                )
                memory_id = cursor.lastrowid
                await conn.commit()

            self.logger.debug("Stored memory entry %s in category %s", memory_id, category)
            return memory_id
        except aiosqlite.Error as e:
            self.logger.error("Failed to store memory entry: %s", e)
            raise RuntimeError(f"Failed to store memory: {e}")

    async def get_memories(
        self,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "timestamp DESC",
    ) -> List[MemoryEntry]:
        """Retrieve memory entries with async querying"""
        await self._init_memory_db()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                if category:
                    query = f"""
                        SELECT id, category, content, metadata, timestamp, reference_path, embedding
                        FROM memory_entries
                        WHERE category = ?
                        ORDER BY {order_by}
                        LIMIT ? OFFSET ?
                    """
                    cursor = await conn.execute(query, (category, limit, offset))
                else:
                    query = f"""
                        SELECT id, category, content, metadata, timestamp, reference_path, embedding
                        FROM memory_entries
                        ORDER BY {order_by}
                        LIMIT ? OFFSET ?
                    """
                    cursor = await conn.execute(query, (limit, offset))

                rows = await cursor.fetchall()
                memories = []
                for row in rows:
                    memories.append(
                        MemoryEntry(
                            id=row[0],
                            category=row[1],
                            content=row[2],
                            metadata=json.loads(row[3]) if row[3] else {},
                            timestamp=datetime.fromtimestamp(row[4]),
                            reference_path=row[5],
                            embedding=row[6],
                        )
                    )

            self.logger.debug("Retrieved %s memory entries", len(memories))
            return memories
        except aiosqlite.Error as e:
            self.logger.error("Failed to get memories: %s", e)
            raise RuntimeError(f"Failed to get memories: {e}")

    async def log_task_execution(
        self,
        task_id: str,
        task_type: str,
        status: str,
        description: str,
        result: Optional[str] = None,
        execution_time_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log task execution with async performance"""
        await self._init_memory_db()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    """
                    INSERT INTO task_logs
                    (task_id, task_type, status, description, result, execution_time_ms,
                     error_message, started_at, completed_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        task_type,
                        status,
                        description,
                        result,
                        execution_time_ms,
                        error_message,
                        (
                            datetime.now()
                            if status in _ACTIVE_STATUSES
                            else None
                        ),
                        datetime.now() if status in _COMPLETED_STATUSES else None,
                        json.dumps(metadata or {}),
                    ),
                )
                log_id = cursor.lastrowid
                await conn.commit()

            self.logger.debug("Logged task execution %s for %s", log_id, task_id)
            return log_id
        except aiosqlite.Error as e:
            self.logger.error("Failed to log task execution for %s: %s", task_id, e)
            raise RuntimeError(f"Failed to log task execution: {e}")

    async def store_agent_state(
        self,
        state_name: str,
        state_data: Dict[str, Any],
        phase: Optional[int] = None,
        active_tasks: Optional[List[str]] = None,
        system_status: str = "idle",
    ) -> int:
        """Store agent state snapshot with async performance"""
        await self._init_memory_db()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    """
                    INSERT INTO agent_states
                    (state_name, state_data, phase, active_tasks, system_status, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state_name,
                        json.dumps(state_data),
                        phase,
                        json.dumps(active_tasks or []),
                        system_status,
                        datetime.now().timestamp(),
                    ),
                )
                state_id = cursor.lastrowid
                await conn.commit()

            self.logger.debug("Stored agent state %s: %s", state_id, state_name)
            return state_id
        except aiosqlite.Error as e:
            self.logger.error("Failed to store agent state %s: %s", state_name, e)
            raise RuntimeError(f"Failed to store agent state: {e}")

    async def log_conversation(
        self,
        session_id: str,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        response_time_ms: Optional[int] = None,
        token_usage: Optional[int] = None,
        model_used: Optional[str] = None,
    ) -> int:
        """Log conversation message with async performance"""
        await self._init_memory_db()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    """
                    INSERT INTO conversation_history
                    (session_id, role, content, timestamp, message_id, response_time_ms, token_usage, model_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        role,
                        content,
                        datetime.now().timestamp(),
                        message_id,
                        response_time_ms,
                        token_usage,
                        model_used,
                    ),
                )
                conv_id = cursor.lastrowid
                await conn.commit()

            self.logger.debug("Logged conversation %s for session %s", conv_id, session_id)
            return conv_id
        except aiosqlite.Error as e:
            self.logger.error("Failed to log conversation for session %s: %s", session_id, e)
            raise RuntimeError(f"Failed to log conversation: {e}")

    async def log_config_change(
        self,
        config_key: str,
        old_value: Optional[str],
        new_value: str,
        change_reason: Optional[str] = None,
    ) -> int:
        """Log configuration changes with async performance"""
        await self._init_memory_db()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    """
                    INSERT INTO config_history
                    (config_key, old_value, new_value, change_reason, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        config_key,
                        old_value,
                        new_value,
                        change_reason,
                        datetime.now().timestamp(),
                    ),
                )
                config_id = cursor.lastrowid
                await conn.commit()

            self.logger.debug("Logged config change %s for %s", config_id, config_key)
            return config_id
        except aiosqlite.Error as e:
            self.logger.error("Failed to log config change for %s: %s", config_key, e)
            raise RuntimeError(f"Failed to log config change: {e}")

    async def cleanup_old_entries(self):
        """Clean up old entries based on retention policies"""
        await self._init_memory_db()

        cutoff_timestamp = (
            datetime.now() - timedelta(days=self.retention_days)
        ).timestamp()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                # Clean up old memory entries
                cursor = await conn.execute(
                    "DELETE FROM memory_entries WHERE timestamp < ?", (cutoff_timestamp,)
                )
                deleted_memory = cursor.rowcount

                # Clean up old task logs
                cursor = await conn.execute(
                    "DELETE FROM task_logs WHERE started_at < ?", (cutoff_timestamp,)
                )
                deleted_tasks = cursor.rowcount

                # Clean up old agent states
                cursor = await conn.execute(
                    "DELETE FROM agent_states WHERE timestamp < ?", (cutoff_timestamp,)
                )
                deleted_states = cursor.rowcount

                # Clean up old conversations
                cursor = await conn.execute(
                    "DELETE FROM conversation_history WHERE timestamp < ?",
                    (cutoff_timestamp,),
                )
                deleted_conversations = cursor.rowcount

                await conn.commit()

                self.logger.info(
                    f"Cleanup completed: {deleted_memory} memories, {deleted_tasks} tasks, "
                    f"{deleted_states} states, {deleted_conversations} conversations"
                )
        except aiosqlite.Error as e:
            self.logger.error("Failed to cleanup old entries: %s", e)
            raise RuntimeError(f"Failed to cleanup old entries: {e}")

    async def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics with async performance"""
        await self._init_memory_db()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                stats = {}

                # Memory entries by category
                cursor = await conn.execute(
                    "SELECT category, COUNT(*) FROM memory_entries GROUP BY category"
                )
                stats["memory_by_category"] = dict(await cursor.fetchall())

                # Task status distribution
                cursor = await conn.execute(
                    "SELECT status, COUNT(*) FROM task_logs GROUP BY status"
                )
                stats["tasks_by_status"] = dict(await cursor.fetchall())

                # Recent activity (last 24 hours)
                recent_timestamp = (datetime.now() - timedelta(hours=24)).timestamp()
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM memory_entries WHERE timestamp > ?",
                    (recent_timestamp,),
                )
                stats["recent_memories"] = (await cursor.fetchone())[0]

                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM conversation_history WHERE timestamp > ?",
                    (recent_timestamp,),
                )
                stats["recent_conversations"] = (await cursor.fetchone())[0]

                return stats
        except aiosqlite.Error as e:
            self.logger.error("Failed to get statistics: %s", e)
            raise RuntimeError(f"Failed to get statistics: {e}")

    async def close(self):
        """Close the async memory manager (cleanup if needed)"""
        # aiosqlite automatically closes connections, no explicit cleanup needed
        self.logger.info("Async memory manager closed")


# Global async memory manager instance (thread-safe)
import threading

_async_memory_manager = None
_async_memory_manager_lock = threading.Lock()


def get_async_memory_manager() -> AsyncLongTermMemoryManager:
    """Get global async memory manager instance (thread-safe)"""
    global _async_memory_manager
    if _async_memory_manager is None:
        with _async_memory_manager_lock:
            # Double-check after acquiring lock
            if _async_memory_manager is None:
                _async_memory_manager = AsyncLongTermMemoryManager()
    return _async_memory_manager
