# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
import pytest_asyncio

from transcriber.database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    await d.connect()
    yield d
    await d.close()


@pytest.mark.asyncio
async def test_create_and_get_project(db):
    pid = await db.create_project("My Project", "A test project", user_id="u1")
    assert isinstance(pid, int)
    project = await db.get_project(pid)
    assert project["name"] == "My Project"
    assert project["description"] == "A test project"
    assert project["user_id"] == "u1"


@pytest.mark.asyncio
async def test_list_projects_user_scoped(db):
    await db.create_project("P1", "", user_id="u1")
    await db.create_project("P2", "", user_id="u2")
    results = await db.list_projects(user_id="u1")
    assert len(results) == 1
    assert results[0]["name"] == "P1"


@pytest.mark.asyncio
async def test_delete_project_cascades(db):
    pid = await db.create_project("P", "", user_id="u1")
    rid = await db.create_recording(pid, "file.wav", "/tmp/file.wav", user_id="u1")
    await db.delete_project(pid)
    assert await db.get_project(pid) is None
    assert await db.get_recording(rid) is None


# ── GH#9056: update/delete raise KeyError on nonexistent ID ───────────────────


@pytest.mark.asyncio
async def test_update_project_missing_raises(db):
    with pytest.raises(KeyError):
        await db.update_project(9999, "x", "y")


@pytest.mark.asyncio
async def test_delete_project_missing_raises(db):
    with pytest.raises(KeyError):
        await db.delete_project(9999)


@pytest.mark.asyncio
async def test_update_recording_status_missing_raises(db):
    with pytest.raises(KeyError):
        await db.update_recording_status(9999, "done")


@pytest.mark.asyncio
async def test_delete_recording_missing_raises(db):
    with pytest.raises(KeyError):
        await db.delete_recording(9999)


@pytest.mark.asyncio
async def test_update_speaker_missing_raises(db):
    with pytest.raises(KeyError):
        await db.update_speaker(9999, "Alice")


@pytest.mark.asyncio
async def test_update_segment_text_missing_raises(db):
    with pytest.raises(KeyError):
        await db.update_segment_text(9999, "hello")


@pytest.mark.asyncio
async def test_update_note_missing_raises(db):
    with pytest.raises(KeyError):
        await db.update_note(9999, "content")


@pytest.mark.asyncio
async def test_delete_note_missing_raises(db):
    with pytest.raises(KeyError):
        await db.delete_note(9999)


# ── GH#9057: schema migration table exists and tracks version ─────────────────


@pytest.mark.asyncio
async def test_migration_table_exists_and_version_recorded(tmp_path):
    import aiosqlite

    db_path = str(tmp_path / "migrate_test.db")
    d = Database(db_path)
    await d.connect()
    await d.close()

    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute("SELECT version FROM _schema_migrations ORDER BY version")
        versions = [row[0] for row in await cur.fetchall()]
    assert versions == [1, 2]


@pytest.mark.asyncio
async def test_migration_idempotent_on_reconnect(tmp_path):
    db_path = str(tmp_path / "idempotent.db")
    for _ in range(3):
        d = Database(db_path)
        await d.connect()
        await d.close()

    import aiosqlite

    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM _schema_migrations")
        row = await cur.fetchone()
    assert row[0] == 2  # migrations 1 and 2 recorded exactly once each


# ── GH#9058: close() uses is not None ────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_idempotent(tmp_path):
    d = Database(str(tmp_path / "close_test.db"))
    await d.connect()
    await d.close()
    await d.close()  # second close must not raise


# ── GH#9059: list methods support limit/offset ────────────────────────────────


@pytest.mark.asyncio
async def test_list_projects_pagination(db):
    for i in range(5):
        await db.create_project(f"P{i}", "", user_id="u1")
    page1 = await db.list_projects(user_id="u1", limit=2, offset=0)
    page2 = await db.list_projects(user_id="u1", limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert {r["name"] for r in page1}.isdisjoint({r["name"] for r in page2})


@pytest.mark.asyncio
async def test_list_recordings_pagination(db):
    pid = await db.create_project("P", "", user_id="u1")
    for i in range(5):
        await db.create_recording(pid, f"f{i}.wav", f"/tmp/f{i}.wav", user_id="u1")
    page1 = await db.list_recordings(pid, limit=2, offset=0)
    page2 = await db.list_recordings(pid, limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert {r["filename"] for r in page1}.isdisjoint({r["filename"] for r in page2})


@pytest.mark.asyncio
async def test_list_segments_pagination(db):
    pid = await db.create_project("P", "", user_id="u1")
    rid = await db.create_recording(pid, "f.wav", "/tmp/f.wav", user_id="u1")
    for i in range(5):
        await db.create_segment(rid, None, float(i), float(i + 1), f"text{i}")
    page1 = await db.list_segments(rid, limit=2, offset=0)
    page2 = await db.list_segments(rid, limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
