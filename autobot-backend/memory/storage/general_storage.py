# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
General Storage Implementation - Category-based memory management
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import aiosqlite

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import parse_utc_iso

from ..enums import MemoryCategory
from ..models import MemoryEntry

logger = get_logger(__name__)

# Owner assigned to rows that predate tenant scoping (#13688). Rows written
# before this column existed have no recoverable owner, so they are parked under
# a reserved id rather than deleted (they stay queryable by asking for this id
# explicitly) and rather than attributed to a real user (which would leak them
# into the first caller's results). Not a valid owner for new writes.
LEGACY_UNSCOPED_OWNER = "__unscoped__"


def _require_user_id(user_id: str) -> str:
    """Validate a caller-supplied owner scope (#13688).

    Raises:
        ValueError: when the scope is missing, blank, or the reserved legacy id
                    used as a write target.
    """
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id is required — memory queries cannot be unscoped")
    return user_id


class GeneralStorage:
    """
    General purpose storage implementation (IGeneralStorage)

    Responsibility: Manage category-based memory in SQLite database

    Tenancy (#13688): every row carries a first-class ``user_id`` column and
    every read applies it as a WHERE predicate. The scope is a required
    argument on each method, so an unscoped query cannot be constructed here —
    isolation does not depend on a call site remembering to filter.
    """

    def __init__(self, db_path: str | Path):
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
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS memory_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata_json TEXT,
                        timestamp TIMESTAMP NOT NULL,
                        reference_path TEXT,
                        embedding BLOB,
                        user_id TEXT NOT NULL DEFAULT '{LEGACY_UNSCOPED_OWNER}'
                    )
                """)  # nosec B608  # interpolates a module constant, never caller input

                await self._migrate_add_user_id(conn)

                # Indexes for common queries
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memory_category
                    ON memory_entries(category)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memory_timestamp
                    ON memory_entries(timestamp)
                """)
                # #13688: every read filters on user_id first, so it leads the index.
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memory_user_category
                    ON memory_entries(user_id, category)
                """)

                await conn.commit()
        except aiosqlite.Error as e:
            logger.error("Failed to initialize general storage: %s", e)
            raise RuntimeError(f"General storage initialization failed: {e}")

    async def _migrate_add_user_id(self, conn) -> None:
        """Add the user_id column to a pre-#13688 database, preserving all rows.

        Databases created before tenant scoping have no user_id column. SQLite
        allows ADD COLUMN with a non-null default, so existing rows are parked
        under LEGACY_UNSCOPED_OWNER instead of being dropped or rewritten — the
        no-data-loss rule. They remain readable by querying that owner.
        """
        cursor = await conn.execute("PRAGMA table_info(memory_entries)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "user_id" in columns:
            return
        await conn.execute(
            "ALTER TABLE memory_entries ADD COLUMN user_id TEXT NOT NULL "
            f"DEFAULT '{LEGACY_UNSCOPED_OWNER}'"  # nosec B608
        )
        logger.info(
            "Migrated memory_entries: added user_id; pre-existing rows parked under %s (#13688)",
            LEGACY_UNSCOPED_OWNER,
        )

    async def store(self, entry: MemoryEntry) -> int:
        """Store memory entry. The entry must carry an owner (#13688)."""
        category_value = entry.category.value if isinstance(entry.category, MemoryCategory) else entry.category
        user_id = _require_user_id(entry.user_id)

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    """
                    INSERT INTO memory_entries (
                        category, content, metadata_json, timestamp,
                        reference_path, embedding, user_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        category_value,
                        entry.content,
                        json.dumps(entry.metadata) if entry.metadata else None,
                        entry.timestamp,
                        entry.reference_path,
                        entry.embedding,
                        user_id,
                    ),
                )
                await conn.commit()

                logger.debug("Stored memory entry: %s (ID: %s)", category_value, cursor.lastrowid)
                return cursor.lastrowid
        except aiosqlite.Error as e:
            logger.error("Failed to store memory entry: %s", e)
            raise RuntimeError(f"Failed to store memory entry: {e}")

    async def retrieve(
        self, user_id: str, category: MemoryCategory | str, filters: Dict[str, Any]
    ) -> List[MemoryEntry]:
        """Retrieve one owner's memories by category and filters (#13688).

        ``user_id`` is required and applied as a WHERE predicate here, so no
        caller can construct a cross-owner query.
        """
        category_value = category.value if isinstance(category, MemoryCategory) else category

        where_clauses = ["user_id = ?", "category = ?"]
        values = [_require_user_id(user_id), category_value]

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
        """  # nosec B608  # clause strings are hardcoded literals; only values are parameterized
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

    async def search(self, user_id: str, query: str) -> List[MemoryEntry]:
        """Search one owner's memories by content or metadata (#13688).

        The owner predicate is bracketed around the content/metadata OR so a
        match on either column still cannot cross an owner boundary.
        """
        owner = _require_user_id(user_id)
        try:
            async with self._get_connection() as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(
                    """
                    SELECT * FROM memory_entries
                    WHERE user_id = ? AND (content LIKE ? OR metadata_json LIKE ?)
                    ORDER BY timestamp DESC
                    LIMIT 100
                """,
                    (owner, f"%{query}%", f"%{query}%"),
                )

                rows = await cursor.fetchall()
                return [self._row_to_entry(row) for row in rows]
        except aiosqlite.Error as e:
            logger.error("Failed to search memory entries: %s", e)
            raise RuntimeError(f"Failed to search memory entries: {e}")

    async def cleanup_old(self, retention_days: int) -> int:
        """Remove entries older than retention period"""
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retention_days)

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("DELETE FROM memory_entries WHERE timestamp < ?", (cutoff,))
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
                cursor = await conn.execute("""
                    SELECT category, COUNT(*)
                    FROM memory_entries
                    GROUP BY category
                """)
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
            timestamp=(parse_utc_iso(row["timestamp"]) if isinstance(row["timestamp"], str) else row["timestamp"]),
            reference_path=row["reference_path"],
            embedding=row["embedding"],
            user_id=row["user_id"],
        )


__all__ = ["GeneralStorage", "LEGACY_UNSCOPED_OWNER"]
