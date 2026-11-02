# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What a deleted conversation file's bytes may do: wait for a human (#20234, #17038).

Deleting a conversation file only marks it (``is_deleted``), and a trigger schedules a
``file_cleanup_queue`` row for every file. Nothing here removes bytes on its own:

* :func:`list_cleanup_candidates` reads the queue -- entries that are due, not yet processed, whose
  file is soft-deleted, and which have not been refused ``AUTOBOT_CONVERSATION_FILE_CLEANUP_MAX_ATTEMPTS``
  times or refused within the cooldown (``file_cleanup_attempts``; a capped file is "stuck" in the stats);
* ``services/conversation_file_cleanup_proposals.py`` turns each into an approval-gate proposal;
* only an APPROVED proposal reaches :func:`remove_approved_file`, which re-validates everything
  at removal time and marks the queue row processed -- the row, the soft-deleted file record,
  the approval and its audit entry are the durable record that outlives the bytes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.env_registry import env
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Refusals per file, durable beside the queue (#20234). CREATE IF NOT EXISTS: an existing install gains
# an empty table and no row of any other table is rewritten.
_ATTEMPTS_DDL = """
    CREATE TABLE IF NOT EXISTS file_cleanup_attempts (
        file_id TEXT PRIMARY KEY,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        last_failed_at TIMESTAMP,
        last_reason TEXT
    )
"""

_CANDIDATES_SQL = """
    SELECT cf.file_id, MIN(fcq.session_id) AS session_id, cf.original_filename, cf.file_size
    FROM file_cleanup_queue fcq
    JOIN conversation_files cf ON cf.file_id = fcq.file_id
    LEFT JOIN file_cleanup_attempts fca ON fca.file_id = cf.file_id
    WHERE fcq.is_processed = 0 AND cf.is_deleted = 1 AND fcq.scheduled_deletion_time <= datetime('now')
      AND COALESCE(fca.failed_attempts, 0) < ?
      AND (fca.last_failed_at IS NULL OR fca.last_failed_at <= datetime('now', ?))
    GROUP BY cf.file_id
    ORDER BY MIN(fcq.cleanup_id)
"""

_PENDING_STATS_SQL = """
    SELECT COUNT(DISTINCT cf.file_id) AS files, COALESCE(SUM(cf.file_size), 0) AS bytes
    FROM conversation_files cf
    WHERE cf.is_deleted = 1
      AND cf.file_id IN (SELECT file_id FROM file_cleanup_queue WHERE is_processed = 0)
"""

_STUCK_SQL = """
    SELECT cf.file_id, cf.file_size, fca.failed_attempts, fca.last_reason
    FROM file_cleanup_attempts fca
    JOIN conversation_files cf ON cf.file_id = fca.file_id
    WHERE fca.failed_attempts >= ? AND cf.is_deleted = 1
      AND cf.file_id IN (SELECT file_id FROM file_cleanup_queue WHERE is_processed = 0)
    ORDER BY fca.last_failed_at DESC
"""

_RECORD_FAILURE_SQL = """
    INSERT INTO file_cleanup_attempts (file_id, failed_attempts, last_failed_at, last_reason)
    VALUES (?, 1, CURRENT_TIMESTAMP, ?)
    ON CONFLICT(file_id) DO UPDATE SET failed_attempts = failed_attempts + 1,
        last_failed_at = CURRENT_TIMESTAMP, last_reason = excluded.last_reason
    RETURNING failed_attempts
"""

#: Most stuck files itemised in the stats; the count is always complete.
_STUCK_LISTED = 50


def cleanup_max_attempts() -> int:
    """Refusals after which a file is no longer proposed (``AUTOBOT_CONVERSATION_FILE_CLEANUP_MAX_ATTEMPTS``)."""
    return max(1, int(env("AUTOBOT_CONVERSATION_FILE_CLEANUP_MAX_ATTEMPTS")))


def cooldown_seconds() -> int:
    """Seconds a refused file waits before it may be proposed again."""
    return max(0, int(env("AUTOBOT_CONVERSATION_FILE_CLEANUP_COOLDOWN_SECONDS")))


async def list_cleanup_candidates(manager) -> List[Dict[str, Any]]:
    """Soft-deleted files whose cleanup is due, unprocessed, and not stuck or cooling down after refusals."""
    connection = await manager._get_async_db_connection()
    try:
        await connection.execute(_ATTEMPTS_DDL)
        params = (cleanup_max_attempts(), f"-{cooldown_seconds()} seconds")
        async with connection.execute(_CANDIDATES_SQL, params) as cursor:
            return [dict(row) for row in await cursor.fetchall()]
    finally:
        await connection.close()


async def pending_cleanup_stats(connection) -> Dict[str, Any]:
    """Deleted files still waiting on the queue (bytes on disk), proposed or not, and those stuck."""
    await connection.execute(_ATTEMPTS_DDL)
    async with connection.execute(_PENDING_STATS_SQL) as cursor:
        row = await cursor.fetchone()
    async with connection.execute(_STUCK_SQL, (cleanup_max_attempts(),)) as cursor:
        stuck = [dict(r) for r in await cursor.fetchall()]
    return {
        "pending_cleanup_files": row["files"] or 0,
        "pending_cleanup_bytes": row["bytes"] or 0,
        "stuck_cleanup_files": len(stuck),
        "stuck_cleanup_bytes": sum(r["file_size"] or 0 for r in stuck),
        "stuck_cleanup": stuck[:_STUCK_LISTED],
    }


async def _record_failure(connection, file_id: str, reason: str) -> None:
    """Count one refused removal; log once when the file reaches the cap and stops being proposed."""
    await connection.execute(_ATTEMPTS_DDL)
    async with connection.execute(_RECORD_FAILURE_SQL, (file_id, reason)) as cursor:
        attempts = (await cursor.fetchone())[0]
    await connection.commit()
    if attempts >= cleanup_max_attempts():
        logger.warning(
            "Conversation file %s is stuck: removal refused %d time(s), last reason: %s; no longer proposed",
            file_id,
            attempts,
            reason,
        )


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


async def _remove_validated(connection, manager, file_id: str, row) -> Dict[str, Any]:
    """Unlink one validated file and mark its queue rows processed, or return the refusal."""
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
    return {"removed": removed, "reason": None if removed else "bytes were already absent", "size": row["file_size"]}


async def remove_approved_file(manager, file_id: str) -> Dict[str, Any]:
    """Remove the bytes of one approved file, re-validated now; a refusal is a result, not a raise.

    Returns ``{"removed": bool, "reason": str | None, "size": int}``. A refused file keeps its
    queue row unprocessed, so it stays visible in the storage stats, and the refusal is counted
    (an unlink error too, which still raises) so a permanent one stops being proposed (#20234).
    """
    async with manager._lock:
        connection = await manager._get_async_db_connection()
        try:
            async with connection.execute(
                "SELECT file_path, file_size, is_deleted FROM conversation_files WHERE file_id = ?", (file_id,)
            ) as cursor:
                row = await cursor.fetchone()
            try:
                result = await _remove_validated(connection, manager, file_id, row)
            except OSError as exc:
                await _record_failure(connection, file_id, f"unlink failed: {exc}")
                raise
            if not result["removed"] and result["reason"] != "bytes were already absent":
                await _record_failure(connection, file_id, result["reason"])
            return result
        finally:
            await connection.close()
