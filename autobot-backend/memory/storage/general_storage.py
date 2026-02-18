# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
General Storage Implementation - Category-based memory management
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Union

import aiosqlite

from ..enums import MemoryCategory
from ..models import MemoryEntry

logger = logging.getLogger(__name__)


class GeneralStorage:
    """
    General purpose storage implementation (IGeneralStorage)

    Responsibility: Manage category-based memory in SQLite database
    """

    def __init__(self, db_path: Union[str, Path]):
        """Initialize general storage with SQLite database path."""
        self.db_path = Path(db_path) if isinstance(db_path, str) else db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self):
        """Get database connection context manager"""
        return aiosqlite.connect(self.db_path)

    async def initialize(self):
        """Initialize memory entries table"""
        try:
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
        except aiosqlite.Error as e:
            logger.error("Failed to initialize general storage: %s", e)
            raise RuntimeError(f"General storage initialization failed: {e}")

    async def store(self, entry: MemoryEntry) -> int:
        """Store memory entry"""
        category_value = (
            entry.category.value
            if isinstance(entry.category, MemoryCategory)
            else entry.category
        )

        try:
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
                    "Stored memory entry: %s (ID: %s)", category_value, cursor.lastrowid
                )
                return cursor.lastrowid
        except aiosqlite.Error as e:
            logger.error("Failed to store memory entry: %s", e)
            raise RuntimeError(f"Failed to store memory entry: {e}")

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

        try:
            async with self._get_connection() as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, values)
                rows = await cursor.fetchall()
                return [self._row_to_entry(row) for row in rows]
        except aiosqlite.Error as e:
            logger.error("Failed to retrieve memory entries: %s", e)
            raise RuntimeError(f"Failed to retrieve memory entries: {e}")

    async def search(self, query: str) -> List[MemoryEntry]:
        """Search memories by content or metadata"""
        try:
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
        except aiosqlite.Error as e:
            logger.error("Failed to search memory entries: %s", e)
            raise RuntimeError(f"Failed to search memory entries: {e}")

    async def cleanup_old(self, retention_days: int) -> int:
        """Remove entries older than retention period"""
        cutoff = datetime.now() - timedelta(days=retention_days)

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "DELETE FROM memory_entries WHERE timestamp < ?", (cutoff,)
                )
                await conn.commit()

                deleted = cursor.rowcount
                if deleted > 0:
                    logger.info(
                        "Cleaned up %s old memory entries (>%s days)",
                        deleted,
                        retention_days,
                    )

                return deleted
        except aiosqlite.Error as e:
            logger.error("Failed to cleanup old memory entries: %s", e)
            raise RuntimeError(f"Failed to cleanup old memory entries: {e}")

    async def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        try:
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
                )
                by_category = {row[0]: row[1] for row in await cursor.fetchall()}

                return {"total_entries": total, "by_category": by_category}
        except aiosqlite.Error as e:
            logger.error("Failed to get storage stats: %s", e)
            raise RuntimeError(f"Failed to get storage stats: {e}")

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


__all__ = ["GeneralStorage"]
