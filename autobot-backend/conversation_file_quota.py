# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The size cap and per-user byte quota on stored conversation files (#20217).

Every way a file enters the store (upload, create, agent-create, copy, content update) ends in
``ConversationFileManager.add_file`` or ``_write_and_update_file``; both call the conditional statements
here, so the quota is enforced where the bytes are recorded, not per route.

What counts against an owner: live files, plus soft-deleted files whose bytes still await removal
(an unprocessed ``file_cleanup_queue`` row, the representation #20234 uses). A deleted file's bytes
leave only through a human-approved proposal (#17038), so nothing here frees or purges anything;
once that removal marks the queue row processed the file stops counting.

Who is charged is ``quota_owner`` (#20678), falling back to ``uploaded_by`` for a row that has none: a
human upload is charged to its uploader as before, and an agent-created file is charged to the human who
owns the conversation (``conversation_file_quota_owner.OWNERLESS_AGENT_WRITE_RULE``), never to the agent's
name, so one user's agent cannot exhaust the quota of another user's. ``uploaded_by`` keeps recording who
wrote the file. A charge owner that is NULL is its own owner: one shared bucket, held to the same quota.
Rows written before #20678 keep their old charge (agent name) until a human approves a proposal (#17038).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict

from fastapi import HTTPException

from autobot_shared.env_registry import env

#: Bytes one owner may keep (``AUTOBOT_CONVERSATION_FILE_USER_QUOTA_BYTES``).
USER_QUOTA_BYTES: int = int(env("AUTOBOT_CONVERSATION_FILE_USER_QUOTA_BYTES"))

#: Stable error codes the frontend maps to translation keys (``utils/conversationFileUpload.ts``).
FILE_TOO_LARGE = "conversation_file_too_large"
QUOTA_EXCEEDED = "conversation_file_quota_exceeded"

# Bytes still on disk for an owner: live files, and deleted files whose removal has not happened.
# The three statements below embed only this module constant; the owner and sizes are bound parameters (B608).
_CHARGED = "COALESCE(quota_owner, uploaded_by)"  # who pays (#20678); a pre-#20678 row has no quota_owner
_HELD = (
    f"{_CHARGED} IS ? AND (is_deleted = 0 OR file_id IN "  # nosec B608 -- constants only, owner is bound
    "(SELECT file_id FROM file_cleanup_queue WHERE is_processed = 0))"
)
_USAGE_SQL = (
    "SELECT COALESCE(SUM(CASE WHEN is_deleted = 0 THEN file_size END), 0), "  # nosec B608
    "COALESCE(SUM(CASE WHEN is_deleted = 1 THEN file_size END), 0) "
    f"FROM conversation_files WHERE {_HELD}"
)
_INSERT_SQL = (
    "INSERT INTO conversation_files (file_id, session_id, original_filename, stored_filename, "  # nosec B608
    "file_path, file_size, file_hash, mime_type, uploaded_by, quota_owner) "
    "SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ? "
    f"WHERE (SELECT COALESCE(SUM(file_size), 0) FROM conversation_files WHERE {_HELD}) + ? <= ?"
)
_RESIZE_SQL = (
    "UPDATE conversation_files SET file_size = ?, file_hash = ? WHERE file_id = ? AND "  # nosec B608
    f"(SELECT COALESCE(SUM(file_size), 0) FROM conversation_files WHERE {_HELD} AND file_id != ?) + ? <= ?"
)


class UploadRefused(HTTPException):
    """HTTP 413 whose ``detail`` is ``{"code", "message", ...figures}``; the code is stable, the message is not."""

    def __init__(self, code: str, message: str, **figures: int) -> None:
        super().__init__(status_code=413, detail={"code": code, "message": message, **figures})


def file_too_large(max_bytes: int) -> UploadRefused:
    """The refusal for a file past the per-file size cap."""
    return UploadRefused(
        FILE_TOO_LARGE, f"File too large. Maximum size: {max_bytes // (1024 * 1024)}MB", max_bytes=max_bytes
    )


def quota_refusal(live: int, pending_removal: int) -> UploadRefused:
    """The refusal for an owner without room, naming live bytes and bytes awaiting human-approved removal apart."""
    message = (
        f"Upload quota exceeded: {live} bytes in use and {pending_removal} bytes of deleted files awaiting "
        f"human review before removal (of {USER_QUOTA_BYTES} allowed)"
    )
    return UploadRefused(
        QUOTA_EXCEEDED,
        message,
        limit_bytes=USER_QUOTA_BYTES,
        live_bytes=live,
        pending_removal_bytes=pending_removal,
        remaining_bytes=max(USER_QUOTA_BYTES - live - pending_removal, 0),
    )


async def usage(connection, owner: str | None) -> Dict[str, int]:
    """Live bytes and pending-removal bytes held for *owner*, kept apart so the message can be true."""
    async with connection.execute(_USAGE_SQL, (owner,)) as cursor:
        live, pending = await cursor.fetchone()
    return {"live": live, "pending_removal": pending}


async def remaining_bytes(connection, owner: str | None) -> int:
    """Bytes *owner* may still store (both kinds counted)."""
    held = await usage(connection, owner)
    return USER_QUOTA_BYTES - held["live"] - held["pending_removal"]


async def _refuse(connection, owner: str | None) -> UploadRefused:
    """The quota refusal carrying *owner*'s current figures."""
    held = await usage(connection, owner)
    return quota_refusal(held["live"], held["pending_removal"])


async def insert_within_quota(connection, record: tuple, owner: str | None, size: int) -> None:
    """Insert the ``conversation_files`` row only if *owner* stays within quota, in ONE statement.

    The sum and the insert are a single SQLite statement, so concurrent writers (other workers, other
    manager instances) cannot each pass a read-then-write check and overshoot; the loser is refused.
    """
    cursor = await connection.execute(_INSERT_SQL, (*record, owner, size, USER_QUOTA_BYTES))
    if cursor.rowcount == 0:
        raise await _refuse(connection, owner)


async def resize_within_quota(connection, row, size: int, file_hash: str) -> None:
    """Set an existing file's size only if its owner stays within quota (a content update can grow it)."""
    owner, file_id = row["quota_owner"] or row["uploaded_by"], row["file_id"]
    cursor = await connection.execute(_RESIZE_SQL, (size, file_hash, file_id, owner, file_id, size, USER_QUOTA_BYTES))
    if cursor.rowcount == 0:
        raise await _refuse(connection, owner)


async def abandon(connection, stored_path: Path, remove_bytes: bool = True) -> None:
    """Roll back a store that failed or was refused, and remove the bytes this call wrote.

    ``remove_bytes`` is False for a deduplicated add: its path is derived from the hash and may be the
    existing file's, which this call did not store.
    """
    await connection.rollback()
    if remove_bytes and await asyncio.to_thread(stored_path.exists):
        await asyncio.to_thread(stored_path.unlink)
