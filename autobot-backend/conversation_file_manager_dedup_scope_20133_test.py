# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Upload dedup is scoped to the uploading session, never the whole table (#20133).

Matching a hash across every session handed user B user A's stored name and a reference to A's file.
Real SQLite and the real schema; only the Redis cache invalidation is stubbed.
"""

from unittest.mock import AsyncMock

import pytest

from conversation_file_manager import ConversationFileManager

_CONTENT = b"known content shared by two people"


@pytest.fixture
async def manager(tmp_path):
    mgr = ConversationFileManager(storage_dir=tmp_path / "storage", db_path=tmp_path / "files.db")
    mgr._initialize_schema()
    mgr._invalidate_session_cache = AsyncMock()
    return mgr


async def _count(mgr, sql, args=()):
    conn = await mgr._get_async_db_connection()
    try:
        async with conn.execute(sql, args) as cur:
            return (await cur.fetchone())[0]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_another_sessions_upload_of_known_content_gets_its_own_record(manager):
    first = await manager.add_file("session-a", _CONTENT, "alice-secret-plan.txt", uploaded_by="alice")
    second = await manager.add_file("session-b", _CONTENT, "notes.txt", uploaded_by="bob")

    assert second["deduplicated"] is False
    assert second["file_id"] != first["file_id"]
    assert second["session_id"] == "session-b"
    assert "alice-secret-plan" not in second["stored_filename"]
    assert "session-a" not in second["file_path"]
    assert "session-b" in second["file_path"]
    assert (
        await _count(manager, "SELECT COUNT(*) FROM session_file_associations WHERE file_id = ?", (first["file_id"],))
        == 1
    )
    assert await _count(manager, "SELECT COUNT(*) FROM conversation_files") == 2


@pytest.mark.asyncio
async def test_the_same_session_still_dedups(manager):
    first = await manager.add_file("session-a", _CONTENT, "one.txt", uploaded_by="alice")
    again = await manager.add_file("session-a", _CONTENT, "two.txt", uploaded_by="alice")

    assert again["deduplicated"] is True
    assert again["file_id"] == first["file_id"]
    assert await _count(manager, "SELECT COUNT(*) FROM conversation_files") == 1


@pytest.mark.asyncio
async def test_deleting_one_session_leaves_the_other_sessions_file(manager):
    await manager.add_file("session-a", _CONTENT, "a.txt", uploaded_by="alice")
    other = await manager.add_file("session-b", _CONTENT, "b.txt", uploaded_by="bob")

    await manager.delete_session_files("session-a", hard_delete=True)

    from pathlib import Path

    assert Path(other["file_path"]).exists()
    assert await _count(manager, "SELECT COUNT(*) FROM conversation_files WHERE file_id = ?", (other["file_id"],)) == 1
