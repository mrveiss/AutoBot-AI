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

# Owner for system-initiated work that has no human requester — scheduled scans,
# background analysis (#13688). Unlike LEGACY_UNSCOPED_OWNER this is *writable*:
# refusing the write instead would discard real results, moving the data loss
# the migration was written to avoid from the read path to the write path. It is
# still an isolated silo, so it never surfaces in a user's results.
SYSTEM_OWNER = "__system__"


def _require_user_id(user_id: str, *, for_write: bool = False) -> str:
    """Validate a caller-supplied owner scope (#13688).

    Returns the *stripped* value: " alice" and "alice" must not become separate
    silos through a stray space.

    ``for_write`` additionally rejects LEGACY_UNSCOPED_OWNER. Reads must keep
    accepting it so parked pre-migration rows stay retrievable, but a write
    under it would re-create the shared unscoped bucket this issue removes.

    Raises:
        ValueError: when the scope is missing, blank, or (on a write) reserved.
    """
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id is required — memory queries cannot be unscoped")
    scoped = user_id.strip()
    if for_write and scoped == LEGACY_UNSCOPED_OWNER:
        raise ValueError(f"{LEGACY_UNSCOPED_OWNER!r} is reserved for pre-migration rows and cannot be written")
    return scoped


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
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS memory_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata_json TEXT,
                        timestamp TIMESTAMP NOT NULL,
                        reference_path TEXT,
                        embedding BLOB,
                        user_id TEXT NOT NULL
                    )
                """)  # #13688: no DEFAULT here — a fresh table must reject an
                # ownerless INSERT outright. The default exists only on the
                # ALTER path, where pre-migration rows genuinely have no owner.

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
        try:
            await conn.execute(
                "ALTER TABLE memory_entries ADD COLUMN user_id TEXT NOT NULL "
                f"DEFAULT '{LEGACY_UNSCOPED_OWNER}'"  # nosec B608
            )
        except aiosqlite.OperationalError as exc:
            # The PRAGMA and the ALTER are not one transaction, and the asyncio
            # lock above this only guards a single process. Two workers coming
            # up together against the same DB both see the column missing and
            # both ALTER; the loser must treat "already there" as success, not
            # as a fatal startup error.
            if "duplicate column name" not in str(exc).lower():
                raise
            logger.debug("memory_entries.user_id already added by a concurrent initializer (#13688)")
            return
        logger.info(
            "Migrated memory_entries: added user_id; pre-existing rows parked under %s (#13688)",
            LEGACY_UNSCOPED_OWNER,
        )

    async def store(self, entry: MemoryEntry) -> int:
        """Store memory entry. The entry must carry an owner (#13688)."""
        category_value = entry.category.value if isinstance(entry.category, MemoryCategory) else entry.category
        user_id = _require_user_id(entry.user_id, for_write=True)

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

    async def list_by_owner(self, user_id: str, limit: int | None = None) -> List[MemoryEntry]:
        """Return every entry belonging to *user_id*, across all categories (#13705).

        The transparency engine needs a user's whole footprint, which neither
        :meth:`retrieve` (category-scoped) nor :meth:`search` (LIKE-scoped) can
        give. Owner-scoped like every other read here — there is no unscoped
        variant to reach for.

        ``limit=None`` (the default) returns everything. A cap here would make
        general the only store in the transparency fan-out that silently
        truncates — the exact under-reporting #13705 exists to fix. Chroma and
        the Redis scans are uncapped, so this matches them.
        """
        owner = _require_user_id(user_id)
        try:
            async with self._get_connection() as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(
                    """
                    SELECT * FROM memory_entries
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """,
                    (owner, limit if limit is not None else -1),  # SQLite: -1 means no limit
                )
                rows = await cursor.fetchall()
                return [self._row_to_entry(row) for row in rows]
        except aiosqlite.Error as e:
            logger.error("Failed to list entries for owner: %s", e)
            raise RuntimeError(f"Failed to list entries for owner: {e}")

    async def delete_for_owner(self, user_id: str, entry_id: int) -> bool:
        """Delete one entry, but only if *user_id* owns it (#13705).

        The owner is part of the WHERE clause rather than checked beforehand, so
        there is no window between the check and the delete and no way to call
        this with an id alone. Returns False when the row does not exist *or*
        belongs to someone else — the caller cannot tell the two apart.

        ``for_write=True`` rejects LEGACY_UNSCOPED_OWNER: reads accept it so
        parked pre-migration rows stay retrievable by an operator, but deletion
        through the transparency engine must not be able to erase a row that
        cannot be attributed to the requester (#13705).
        """
        owner = _require_user_id(user_id, for_write=True)
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "DELETE FROM memory_entries WHERE id = ? AND user_id = ?", (entry_id, owner)
                )
                await conn.commit()
                return cursor.rowcount > 0
        except aiosqlite.Error as e:
            logger.error("Failed to delete entry for owner: %s", e)
            raise RuntimeError(f"Failed to delete entry for owner: {e}")

    async def cleanup_old(self, retention_days: int) -> int:
        """Remove entries older than retention period, across all owners.

        Operator-scope by design: retention is a storage policy, not a tenant
        query, so this is the one method that spans owners deliberately.

        #13688: rows parked under LEGACY_UNSCOPED_OWNER are exempt. They are by
        definition older than any retention window, so without this the first
        sweep after the upgrade would delete every pre-migration row — silent
        data loss caused by the migration that was supposed to preserve them.
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retention_days)

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "DELETE FROM memory_entries WHERE timestamp < ? AND user_id != ?",
                    (cutoff, LEGACY_UNSCOPED_OWNER),
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
        """Get storage statistics across all owners.

        #13688: operator-scope aggregate, deliberately not tenant-filtered — it
        returns counts only, never content. A per-owner variant should be added
        if this is ever surfaced to end users rather than to operators.
        """
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


__all__ = ["GeneralStorage", "LEGACY_UNSCOPED_OWNER", "SYSTEM_OWNER"]
