# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What a deleted conversation file's bytes may do: wait for a human (#20234, #17038).

Deleting a conversation file only marks it (``is_deleted``), and a trigger schedules a
``file_cleanup_queue`` row for every file. Nothing here removes bytes on its own:

* :func:`list_cleanup_candidates` reads the queue (read-only) -- entries that are due, not yet
  processed, and whose file is soft-deleted;
* ``services/conversation_file_cleanup_proposals.py`` turns each into an approval-gate proposal;
* only an APPROVED proposal reaches :func:`remove_approved_file`, which re-validates everything
  at removal time and marks the queue row processed -- the row, the soft-deleted file record,
  the approval and its audit entry are the durable record that outlives the bytes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_CANDIDATES_SQL = """
    SELECT cf.file_id, MIN(fcq.session_id) AS session_id, cf.original_filename, cf.file_size
    FROM file_cleanup_queue fcq
    JOIN conversation_files cf ON cf.file_id = fcq.file_id
    WHERE fcq.is_processed = 0 AND cf.is_deleted = 1 AND fcq.scheduled_deletion_time <= datetime('now')
    GROUP BY cf.file_id
    ORDER BY MIN(fcq.cleanup_id)
"""

_PENDING_STATS_SQL = """
    SELECT COUNT(DISTINCT cf.file_id) AS files, COALESCE(SUM(cf.file_size), 0) AS bytes
    FROM conversation_files cf
    WHERE cf.is_deleted = 1
      AND cf.file_id IN (SELECT file_id FROM file_cleanup_queue WHERE is_processed = 0)
"""


async def list_cleanup_candidates(manager) -> List[Dict[str, Any]]:
    """Soft-deleted files whose cleanup is due and unprocessed. Read-only."""
    connection = await manager._get_async_db_connection()
    try:
        async with connection.execute(_CANDIDATES_SQL) as cursor:
            return [dict(row) for row in await cursor.fetchall()]
    finally:
        await connection.close()


async def pending_cleanup_stats(connection) -> Dict[str, int]:
    """Deleted files still waiting on the queue (bytes still on disk), proposed yet or not."""
    async with connection.execute(_PENDING_STATS_SQL) as cursor:
        row = await cursor.fetchone()
    return {"pending_cleanup_files": row["files"] or 0, "pending_cleanup_bytes": row["bytes"] or 0}


async def deleted_file_stats(connection) -> tuple:
    """Deleted file count and size."""
    query = (
        "SELECT COUNT(*) as deleted_files, SUM(file_size) as deleted_size "
        "FROM conversation_files WHERE is_deleted = 1"
    )
    async with connection.execute(query) as cursor:
        row = await cursor.fetchone()
    return row["deleted_files"] or 0, row["deleted_size"] or 0


def _contained_file(storage_dir: Path, stored_path: str) -> Path | None:
    """The resolved path when it is strictly inside the store, else ``None``."""
    resolved = Path(stored_path).resolve()
    root = storage_dir.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        return None
    return resolved


async def _refusal(connection, file_id: str, row) -> str | None:
    """Why this file must NOT be removed, or ``None`` when it may be."""
    if row is None:
        return "no such file record"
    if not row["is_deleted"]:
        return "file is live (restored or never deleted)"
    async with connection.execute(
        "SELECT 1 FROM conversation_files WHERE file_path = ? AND file_id != ? AND is_deleted = 0 LIMIT 1",
        (row["file_path"], file_id),
    ) as cursor:
        if await cursor.fetchone():
            return "file is still referenced by a live record"
    return None


def _unlink_contained(storage_dir: Path, stored_path: str) -> str:
    """Remove the file if (and only if) it resolves inside the store NOW. Returns the outcome."""
    target = _contained_file(storage_dir, stored_path)
    if target is None:
        return "outside"
    if not target.exists():
        return "absent"
    if not target.is_file():
        return "outside"
    target.unlink()
    return "removed"


async def remove_approved_file(manager, file_id: str) -> Dict[str, Any]:
    """Remove the bytes of one approved file, re-validated now; a refusal is a result, not a raise.

    Returns ``{"removed": bool, "reason": str | None, "size": int}``. A refused file keeps its
    queue row unprocessed, so it stays visible in the storage stats.
    """
    async with manager._lock:
        connection = await manager._get_async_db_connection()
        try:
            async with connection.execute(
                "SELECT file_path, file_size, is_deleted FROM conversation_files WHERE file_id = ?", (file_id,)
            ) as cursor:
                row = await cursor.fetchone()
            reason = await _refusal(connection, file_id, row)
            if reason:
                return {"removed": False, "reason": reason, "size": 0}
            outcome = await asyncio.to_thread(_unlink_contained, manager.storage_dir, row["file_path"])
            if outcome == "outside":
                logger.error("Refused to remove %s: its stored path is outside the conversation file store", file_id)
                return {"removed": False, "reason": "path is outside the conversation file store", "size": 0}
            await connection.execute(
                "UPDATE file_cleanup_queue SET is_processed = 1, processed_at = CURRENT_TIMESTAMP "
                "WHERE file_id = ? AND is_processed = 0",
                (file_id,),
            )
            await connection.commit()
            removed = outcome == "removed"
            return {
                "removed": removed,
                "reason": None if removed else "bytes were already absent",
                "size": row["file_size"],
            }
        finally:
            await connection.close()
