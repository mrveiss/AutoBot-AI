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
