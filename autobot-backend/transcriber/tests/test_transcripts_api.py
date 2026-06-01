# autobot-backend/transcriber/tests/test_transcripts_api.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from transcriber.routes.transcripts import router
from transcriber.database import Database
from transcriber.deps import get_db


@pytest_asyncio.fixture
async def client(tmp_path):
    a = FastAPI()
    db = Database(str(tmp_path / "test.db"))

    async def override_db():
        return db

    await db.connect()
    a.dependency_overrides[get_db] = override_db
    a.include_router(router, prefix="/api/transcriber")

    # Create test data
    pid = await db.create_project("P", "", "u1")
    rid = await db.create_recording(pid, "a.wav", "/tmp/a.wav", "u1")
    sid = await db.create_speaker(rid, "SPEAKER_00", "Alice", "lv")
    await db.create_segment(rid, sid, 0.0, 1.5, "Hello world")
    a.state._test_rid = rid
    a.state._test_sid = sid

    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_get_transcript(client, tmp_path):
    rid = client._transport.app.state._test_rid  # type: ignore
    r = await client.get(f"/api/transcriber/recordings/{rid}/transcript")
    assert r.status_code == 200
    data = r.json()
    assert len(data["segments"]) == 1
    assert data["segments"][0]["text"] == "Hello world"
    assert data["speakers"][0]["display_name"] == "Alice"


@pytest.mark.asyncio
async def test_update_segment_text(client, tmp_path):
    rid = client._transport.app.state._test_rid  # type: ignore
    transcript = (await client.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
    seg_id = transcript["segments"][0]["id"]
    r = await client.patch(f"/api/transcriber/segments/{seg_id}", json={"text": "Updated text"})
    assert r.status_code == 200
    assert r.json()["is_edited"] is True
    assert r.json()["text"] == "Updated text"


@pytest.mark.asyncio
async def test_rename_speaker(client, tmp_path):
    sid = client._transport.app.state._test_sid  # type: ignore
    r = await client.patch(f"/api/transcriber/speakers/{sid}", json={"display_name": "Bob"})
    assert r.status_code == 200
    assert r.json()["display_name"] == "Bob"


@pytest.mark.asyncio
async def test_create_and_delete_note(client, tmp_path):
    rid = client._transport.app.state._test_rid  # type: ignore
    transcript = (await client.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
    seg_id = transcript["segments"][0]["id"]
    r = await client.post(f"/api/transcriber/segments/{seg_id}/notes",
                         json={"content": "Important!", "recording_id": rid})
    assert r.status_code == 201
    note_id = r.json()["id"]
    r2 = await client.delete(f"/api/transcriber/notes/{note_id}")
    assert r2.status_code == 204


@pytest.mark.asyncio
async def test_merge_speakers(client, tmp_path):
    # Get database instance from the app
    app = client._transport.app  # type: ignore
    db_dep = app.dependency_overrides[get_db]
    db = await db_dep()

    # Create a second speaker and segments for both
    rid = app.state._test_rid
    sid1 = app.state._test_sid  # Alice
    sid2 = await db.create_speaker(rid, "SPEAKER_01", "Bob", "lv")

    # Create segments for both speakers
    seg1 = await db.create_segment(rid, sid1, 1.5, 3.0, "Alice says this")
    seg2 = await db.create_segment(rid, sid2, 3.0, 5.0, "Bob says this")
    seg3 = await db.create_segment(rid, sid2, 5.0, 7.0, "Bob says more")

    # Verify initial state
    transcript = (await client.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
    assert len(transcript["speakers"]) == 2
    assert len(transcript["segments"]) == 4  # 1 from fixture + 3 new

    # Merge Bob into Alice (source=sid2, target=sid1)
    r = await client.post("/api/transcriber/speakers/merge",
                          json={"source_speaker_id": sid2, "target_speaker_id": sid1})
    assert r.status_code == 200
    assert r.json()["success"] is True

    # Verify speakers after merge
    transcript_after = (await client.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
    assert len(transcript_after["speakers"]) == 1  # Bob was deleted
    assert transcript_after["speakers"][0]["id"] == sid1  # Only Alice remains

    # Verify all segments now point to Alice
    for seg in transcript_after["segments"]:
        assert seg["speaker_id"] == sid1


@pytest.mark.asyncio
async def test_merge_speakers_from_different_recordings_fails(client, tmp_path):
    # Get database instance
    app = client._transport.app  # type: ignore
    db_dep = app.dependency_overrides[get_db]
    db = await db_dep()

    # Create a second recording with a speaker
    rid1 = app.state._test_rid
    sid1 = app.state._test_sid

    pid = await db.create_project("P2", "", "u1")
    rid2 = await db.create_recording(pid, "b.wav", "/tmp/b.wav", "u1")
    sid2 = await db.create_speaker(rid2, "SPEAKER_00", "Charlie", "en")

    # Try to merge speakers from different recordings
    r = await client.post("/api/transcriber/speakers/merge",
                          json={"source_speaker_id": sid2, "target_speaker_id": sid1})
    assert r.status_code == 400
    assert "different recordings" in r.json()["detail"]
