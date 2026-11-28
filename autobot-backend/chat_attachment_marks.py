# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The durable per-chat "an attachment turn ran here" mark (#20195).

System of record: the ``chat_attachment_marks`` table of the conversation files SQLite store
(``autobot_shared.store_authority`` concept ``chat_attachment_use``). It is keyed by chat id alone, so it does not
depend on a session record existing yet (a new chat's first turn), on any file row (file deletion removes the
association), or on a cache. There is no other copy.

Migration: ``CREATE TABLE IF NOT EXISTS`` runs on every access (and is also in the schema file for new installs), so an
existing ``conversation_files.db`` without the table gets it on the first mark or read. No data is rewritten.
"""

from __future__ import annotations

_CREATE = """
CREATE TABLE IF NOT EXISTS chat_attachment_marks (
    session_id TEXT PRIMARY KEY,
    first_marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


async def write_mark(manager, session_id: str) -> None:
    """Record, idempotently, that *session_id* ran an attachment turn. Raises when the write did not commit."""
    connection = await manager._get_async_db_connection()
    try:
        await connection.execute(_CREATE)
        await connection.execute("INSERT OR IGNORE INTO chat_attachment_marks (session_id) VALUES (?)", (session_id,))
        await connection.commit()
    finally:
        await connection.close()


async def read_mark(manager, session_id: str) -> bool:
    """Whether *session_id* is marked. Raises when the store cannot be read: the caller asks."""
    connection = await manager._get_async_db_connection()
    try:
        await connection.execute(_CREATE)
        async with connection.execute(
            "SELECT 1 FROM chat_attachment_marks WHERE session_id = ? LIMIT 1", (session_id,)
        ) as cursor:
            return await cursor.fetchone() is not None
    finally:
        await connection.close()
