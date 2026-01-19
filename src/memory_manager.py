# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# src/memory_manager.py
"""
Comprehensive Long-Term Memory Manager for AutoBot Agent

This module establishes SQLite as the primary long-term memory backend,
handling task logs, execution history, agent state, configuration changes,
and knowledge base integration with optional embedding storage.
"""

import hashlib
import json
import logging
import os
import pickle  # Still imported for backward compatibility, but using JSON for new data
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


# Import the centralized ConfigManager
from src.config import config as global_config_manager

# Import shared path utilities
from src.utils.common import PathUtils

# Import database pooling for performance
from src.utils.database_pool import get_connection_pool

# Performance optimization: O(1) lookup for terminal task statuses (Issue #326)
TERMINAL_TASK_STATUSES = {"DONE", "FAILED"}


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


class LongTermMemoryManager:
    """
    Centralized long-term memory system using SQLite as the primary backend.
    Integrates with existing knowledge base and extends to cover all agent memory needs.
    """

    def __init__(self, config_path: Optional[str] = None):
        """Initialize long-term memory manager with SQLite backend."""
        # Use centralized configuration manager
        self.config = global_config_manager.to_dict()

        # Memory database path from centralized config
        memory_config = self.config.get("memory", {})
        data_config = self.config.get("data", {})
        default_db_path = os.getenv("AUTOBOT_LONG_TERM_DB_PATH", "data/agent_memory.db")
        self.db_path = PathUtils.resolve_path(
            memory_config.get("long_term_db_path")
            or data_config.get("long_term_db_path", default_db_path)
        )

        # Memory retention settings
        self.retention_days = memory_config.get("retention_days", 90)
        self.max_entries_per_category = memory_config.get(
            "max_entries_per_category", 10000
        )

        # Initialize database setup
        self._initialized = False

        logging.info(f"Long-term memory manager initialized at {self.db_path}")

    def _init_memory_db(self):
        """Initialize SQLite database with comprehensive memory tables"""
        if self._initialized:
            return

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        self._configure_db_pragmas(cursor)
        self._create_memory_tables(cursor)
        self._create_memory_indexes(cursor)

        conn.commit()
        conn.close()

        self._initialized = True
        logging.info("Long-term memory database initialized successfully")

    def _configure_db_pragmas(self, cursor: sqlite3.Cursor):
        """Configure SQLite pragmas for better performance"""
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=10000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA foreign_keys=ON")

    def _create_memory_tables(self, cursor: sqlite3.Cursor):
        """Create all memory-related tables"""
        self._create_memory_entries_table(cursor)
        self._create_task_logs_table(cursor)
        self._create_agent_states_table(cursor)
        self._create_config_history_table(cursor)
        self._create_conversations_table(cursor)
        self._create_markdown_refs_table(cursor)

    def _create_memory_entries_table(self, cursor: sqlite3.Cursor):
        """Create main memory entries table"""
        cursor.execute(
            """
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
            """
        )

    def _create_task_logs_table(self, cursor: sqlite3.Cursor):
        """Create task execution logs table"""
        cursor.execute(
            """
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
            """
        )

    def _create_agent_states_table(self, cursor: sqlite3.Cursor):
        """Create agent state snapshots table"""
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state_name TEXT NOT NULL,
                state_data TEXT NOT NULL,
                phase INTEGER,
                active_tasks TEXT,
                system_status TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _create_config_history_table(self, cursor: sqlite3.Cursor):
        """Create configuration change history table"""
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS config_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_section TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                changed_by TEXT,
                change_reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _create_conversations_table(self, cursor: sqlite3.Cursor):
        """Create conversation memory table for LLM interactions"""
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                model_used TEXT,
                tokens_used INTEGER,
                response_time_ms INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _create_markdown_refs_table(self, cursor: sqlite3.Cursor):
        """Create markdown file references table"""
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS markdown_refs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                line_start INTEGER,
                line_end INTEGER,
                content_excerpt TEXT,
                memory_entry_id INTEGER,
                last_modified DATETIME,
                FOREIGN KEY (memory_entry_id) REFERENCES memory_entries (id)
            )
            """
        )

    def _create_memory_indexes(self, cursor: sqlite3.Cursor):
        """Create indexes for memory tables"""
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_category ON memory_entries(category)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_timestamp ON memory_entries(timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_status ON task_logs(status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_type ON task_logs(task_type)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversation_session ON conversations(session_id)"
        )

    def store_memory(
        self,
        category: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        reference_path: Optional[str] = None,
        embedding: Optional[List[float]] = None,
    ) -> int:
        """
        Store a memory entry in the long-term database

        Args:
            category: Type of memory ('task', 'execution', 'state',
                      'config', 'fact', 'conversation')
            content: The actual content to store
            metadata: Additional metadata as dictionary
            reference_path: Path to referenced markdown file
            embedding: Optional embedding vector for semantic search

        Returns:
            ID of stored memory entry
        """
        # Initialize database if needed
        self._init_memory_db()

        # Use connection pool for better performance
        pool = get_connection_pool(self.db_path)
        with pool.get_connection() as conn:
            cursor = conn.cursor()

            try:
                # Create content hash for duplicate detection
                content_hash = hashlib.sha256(content.encode()).hexdigest()

                # Serialize metadata and embedding
                metadata_json = json.dumps(metadata) if metadata else None
                embedding_blob = pickle.dumps(embedding) if embedding else None

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO memory_entries
                    (category, content, metadata, reference_path, embedding, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        category,
                        content,
                        metadata_json,
                        reference_path,
                        embedding_blob,
                        content_hash,
                    ),
                )

                entry_id = cursor.lastrowid
                conn.commit()

                if entry_id is None:
                    raise RuntimeError("Failed to get lastrowid after insert")

                logging.info(f"Stored memory entry {entry_id} in category '{category}'")
                return entry_id

            except Exception as e:
                logging.error(f"Error storing memory: {str(e)}")
                raise

    def retrieve_memory(
        self,
        category: Optional[str] = None,
        limit: int = 100,
        days_back: Optional[int] = None,
    ) -> List[MemoryEntry]:
        """
        Retrieve memory entries with optional filtering

        Args:
            category: Filter by category
            limit: Maximum number of entries to return
            days_back: Only return entries from last N days

        Returns:
            List of MemoryEntry objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            query = (
                "SELECT id, category, content, metadata, timestamp, "
                "reference_path, embedding FROM memory_entries"
            )
            params = []

            conditions = []
            if category:
                conditions.append("category = ?")
                params.append(category)

            if days_back:
                cutoff_date = datetime.now() - timedelta(days=days_back)
                conditions.append("timestamp >= ?")
                params.append(cutoff_date.isoformat())

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            memories = []
            for row in rows:
                memory = MemoryEntry(
                    id=row[0],
                    category=row[1],
                    content=row[2],
                    metadata=json.loads(row[3]) if row[3] else {},
                    timestamp=datetime.fromisoformat(row[4]),
                    reference_path=row[5],
                    embedding=pickle.loads(row[6]) if row[6] else None,
                )
                memories.append(memory)

            logging.info(f"Retrieved {len(memories)} memory entries")
            return memories

        except Exception as e:
            logging.error(f"Error retrieving memory: {str(e)}")
            return []
        finally:
            conn.close()

    def store_task_log(
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
        """Store task execution log"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            metadata_json = json.dumps(metadata) if metadata else None

            cursor.execute(
                """
                INSERT INTO task_logs
                (task_id, task_type, status, description, result,
                 execution_time_ms, error_message, started_at, completed_at,
                 metadata)
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
                    datetime.now().isoformat(),
                    (
                        datetime.now().isoformat()
                        if status in TERMINAL_TASK_STATUSES
                        else None
                    ),
                    metadata_json,
                ),
            )

            log_id = cursor.lastrowid
            conn.commit()

            if log_id is None:
                raise RuntimeError("Failed to get lastrowid after insert")

            logging.info(f"Stored task log {log_id} for task {task_id}")
            return log_id

        except Exception as e:
            logging.error(f"Error storing task log: {str(e)}")
            raise
        finally:
            conn.close()

    def store_agent_state(
        self,
        state_name: str,
        state_data: Dict[str, Any],
        phase: int,
        active_tasks: List[str],
        system_status: str,
    ) -> int:
        """Store agent state snapshot"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO agent_states
                (state_name, state_data, phase, active_tasks, system_status)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    state_name,
                    json.dumps(state_data),
                    phase,
                    json.dumps(active_tasks),
                    system_status,
                ),
            )

            state_id = cursor.lastrowid
            conn.commit()

            if state_id is None:
                raise RuntimeError("Failed to get lastrowid after insert")

            logging.info(f"Stored agent state {state_id}")
            return state_id

        except Exception as e:
            logging.error(f"Error storing agent state: {str(e)}")
            raise
        finally:
            conn.close()

    def store_config_change(
        self,
        config_section: str,
        old_value: str,
        new_value: str,
        changed_by: str,
        change_reason: str,
    ) -> int:
        """Store configuration change history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO config_history
                (config_section, old_value, new_value, changed_by, change_reason)
                VALUES (?, ?, ?, ?, ?)
            """,
                (config_section, old_value, new_value, changed_by, change_reason),
            )

            change_id = cursor.lastrowid
            conn.commit()

            if change_id is None:
                raise RuntimeError("Failed to get lastrowid after insert")

            logging.info(
                f"Stored config change {change_id} for section " f"'{config_section}'"
            )
            return change_id

        except Exception as e:
            logging.error(f"Error storing config change: {str(e)}")
            raise
        finally:
            conn.close()

    def store_conversation(
        self,
        session_id: str,
        role: str,
        message: str,
        model_used: Optional[str] = None,
        tokens_used: Optional[int] = None,
        response_time_ms: Optional[int] = None,
    ) -> int:
        """Store conversation entry for LLM interactions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO conversations
                (session_id, role, message, model_used, tokens_used, response_time_ms)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (session_id, role, message, model_used, tokens_used, response_time_ms),
            )

            conversation_id = cursor.lastrowid
            conn.commit()

            if conversation_id is None:
                raise RuntimeError("Failed to get lastrowid after insert")

            logging.info(f"Stored conversation entry {conversation_id}")
            return conversation_id

        except Exception as e:
            logging.error(f"Error storing conversation: {str(e)}")
            raise
        finally:
            conn.close()

    def link_markdown_reference(
        self,
        memory_entry_id: int,
        file_path: str,
        line_start: int,
        line_end: int,
        content_excerpt: str,
    ) -> int:
        """Link a memory entry to a markdown file reference"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get file modification time
            if os.path.exists(file_path):
                last_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
            else:
                last_modified = datetime.now()

            cursor.execute(
                """
                INSERT INTO markdown_refs
                (file_path, line_start, line_end, content_excerpt,
                 memory_entry_id, last_modified)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    file_path,
                    line_start,
                    line_end,
                    content_excerpt,
                    memory_entry_id,
                    last_modified.isoformat(),
                ),
            )

            ref_id = cursor.lastrowid
            conn.commit()

            if ref_id is None:
                raise RuntimeError("Failed to get lastrowid after insert")

            logging.info(
                f"Linked markdown reference {ref_id} to memory entry "
                f"{memory_entry_id}"
            )
            return ref_id

        except Exception as e:
            logging.error(f"Error linking markdown reference: {str(e)}")
            raise
        finally:
            conn.close()

    def search_memory(
        self, query: str, category: Optional[str] = None
    ) -> List[MemoryEntry]:
        """
        Search memory entries using text search
        Future enhancement: Could add semantic search using embeddings
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            base_query = """
                SELECT id, category, content, metadata, timestamp,
                       reference_path, embedding
                FROM memory_entries
                WHERE content LIKE ?
            """
            params = [f"%{query}%"]

            if category:
                base_query += " AND category = ?"
                params.append(category)

            base_query += " ORDER BY timestamp DESC LIMIT 50"

            cursor.execute(base_query, params)
            rows = cursor.fetchall()

            memories = []
            for row in rows:
                memory = MemoryEntry(
                    id=row[0],
                    category=row[1],
                    content=row[2],
                    metadata=json.loads(row[3]) if row[3] else {},
                    timestamp=datetime.fromisoformat(row[4]),
                    reference_path=row[5],
                    embedding=pickle.loads(row[6]) if row[6] else None,
                )
                memories.append(memory)

            logging.info(
                f"Found {len(memories)} memory entries matching query: '{query}'"
            )
            return memories

        except Exception as e:
            logging.error(f"Error searching memory: {str(e)}")
            return []
        finally:
            conn.close()

    def cleanup_old_entries(self) -> int:
        """Clean up old memory entries based on retention policy"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)

            # Clean up old memory entries
            cursor.execute(
                """
                DELETE FROM memory_entries
                WHERE timestamp < ? AND category NOT IN ('config', 'state')
            """,
                (cutoff_date.isoformat(),),
            )

            deleted_count = cursor.rowcount

            # Clean up old task logs
            cursor.execute(
                "DELETE FROM task_logs WHERE completed_at < ?",
                (cutoff_date.isoformat(),),
            )

            # Clean up old conversations (keep more recent ones)
            conversation_cutoff = datetime.now() - timedelta(
                days=self.retention_days // 2
            )
            cursor.execute(
                "DELETE FROM conversations WHERE timestamp < ?",
                (conversation_cutoff.isoformat(),),
            )

            conn.commit()

            logging.info(f"Cleaned up {deleted_count} old memory entries")
            return deleted_count

        except Exception as e:
            logging.error(f"Error cleaning up old entries: {str(e)}")
            return 0
        finally:
            conn.close()

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get statistics about memory usage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            stats = {}

            # Memory entries by category
            cursor.execute(
                """
                SELECT category, COUNT(*)
                FROM memory_entries
                GROUP BY category
            """
            )
            stats["entries_by_category"] = dict(cursor.fetchall())

            # Total memory entries
            cursor.execute("SELECT COUNT(*) FROM memory_entries")
            stats["total_entries"] = cursor.fetchone()[0]

            # Task completion rates
            cursor.execute(
                """
                SELECT status, COUNT(*)
                FROM task_logs
                GROUP BY status
            """
            )
            stats["task_status_counts"] = dict(cursor.fetchall())

            # Database size
            cursor.execute(
                "SELECT page_count * page_size as size FROM "
                "pragma_page_count(), pragma_page_size()"
            )
            stats["database_size_bytes"] = cursor.fetchone()[0]

            # Recent activity (last 7 days)
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            cursor.execute(
                "SELECT COUNT(*) FROM memory_entries WHERE timestamp >= ?",
                (week_ago,),
            )
            stats["recent_entries"] = cursor.fetchone()[0]

            return stats

        except Exception as e:
            logging.error(f"Error getting memory stats: {str(e)}")
            return {}
        finally:
            conn.close()


# Integration utility functions (thread-safe)
import threading

_memory_manager_instance: Optional[LongTermMemoryManager] = None
_memory_manager_lock = threading.Lock()



def get_memory_manager() -> LongTermMemoryManager:
    """Get singleton instance of memory manager (thread-safe)"""
    global _memory_manager_instance
    if _memory_manager_instance is None:
        with _memory_manager_lock:
            # Double-check after acquiring lock
            if _memory_manager_instance is None:
                _memory_manager_instance = LongTermMemoryManager()
    return _memory_manager_instance


def log_task_completion(
    task_id: str, task_type: str, description: str, result: str, execution_time_ms: int
) -> int:
    """Convenience function to log task completion"""
    memory_manager = get_memory_manager()
    return memory_manager.store_task_log(
        task_id=task_id,
        task_type=task_type,
        status="DONE",
        description=description,
        result=result,
        execution_time_ms=execution_time_ms,
    )


def store_agent_thought(thought: str, context: Dict[str, Any]) -> int:
    """Convenience function to store agent reasoning/thoughts"""
    memory_manager = get_memory_manager()
    return memory_manager.store_memory(
        category="thought", content=thought, metadata=context
    )


# Example usage and testing
if __name__ == "__main__":
    # Initialize memory manager
    memory_mgr = LongTermMemoryManager()

    # Test storing different types of memories
    print("Testing Long-Term Memory Manager...")

    # Store a task log
    task_id = memory_mgr.store_task_log(
        task_id="task_001",
        task_type="gui_automation",
        status="DONE",
        description="Automated mouse click on button",
        result="Successfully clicked button at coordinates (100, 200)",
        execution_time_ms=1500,
    )
    print(f"Stored task log with ID: {task_id}")

    # Store agent state
    state_id = memory_mgr.store_agent_state(
        state_name="active_execution",
        state_data={"current_task": "gui_automation", "steps_completed": 5},
        phase=4,
        active_tasks=["task_001", "task_002"],
        system_status="busy",
    )
    print(f"Stored agent state with ID: {state_id}")

    # Store a configuration change
    config_id = memory_mgr.store_config_change(
        config_section="llm.model",
        old_value="gpt-3.5-turbo",
        new_value="gpt-4",
        changed_by="user",
        change_reason="Better performance needed",
    )
    print(f"Stored config change with ID: {config_id}")

    # Store a memory entry with markdown reference
    memory_id = memory_mgr.store_memory(
        category="fact",
        content="AutoBot uses SQLite as primary long-term memory backend",
        metadata={"source": "implementation", "verified": True},
        reference_path="docs/tasks.md",
    )
    print(f"Stored memory entry with ID: {memory_id}")

    # Link to markdown file
    ref_id = memory_mgr.link_markdown_reference(
        memory_entry_id=memory_id,
        file_path="docs/tasks.md",
        line_start=15,
        line_end=17,
        content_excerpt="Define SQLite as Long-Term Memory",
    )
    print(f"Linked markdown reference with ID: {ref_id}")

    # Test retrieval
    print("\nTesting memory retrieval...")
    memories = memory_mgr.retrieve_memory(category="fact", limit=10)
    for memory in memories:
        print(f"Memory: {memory.content[:50]}... (ID: {memory.id})")

    # Test search
    print("\nTesting memory search...")
    search_results = memory_mgr.search_memory("SQLite")
    for result in search_results:
        print(f"Found: {result.content[:50]}...")

    # Get statistics
    print("\nMemory statistics:")
    stats = memory_mgr.get_memory_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")
