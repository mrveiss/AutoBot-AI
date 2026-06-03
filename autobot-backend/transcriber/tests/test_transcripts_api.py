# autobot-backend/transcriber/tests/test_transcripts_api.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
import pytest_asyncio
from types import SimpleNamespace
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from transcriber.routes.transcripts import router
from transcriber.database import Database
from transcriber.deps import get_db


def _make_app(tmp_path, user_id: str = "u1"):
    a = FastAPI()
    db = Database(str(tmp_path / "test.db"))

    async def override_db():
        return db

    a.dependency_overrides[get_db] = override_db
    a.include_router(router, prefix="/api/transcriber")
    a.state._db = db
    a.state._user_id = user_id
    return a


@pytest_asyncio.fixture
async def client(tmp_path):
    a = _make_app(tmp_path, user_id="u1")
    db = a.state._db
    await db.connect()

    # Create test data owned by u1
    pid = await db.create_project("P", "", "u1")
    rid = await db.create_recording(pid, "a.wav", "/tmp/a.wav", "u1")
    sid = await db.create_speaker(rid, "SPEAKER_00", "Alice", "lv")
    await db.create_segment(rid, sid, 0.0, 1.5, "Hello world")
    a.state._test_rid = rid
    a.state._test_sid = sid

    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        # Inject user into request state via middleware shim
        @a.middleware("http")
        async def inject_user(request, call_next):
            request.state.user = SimpleNamespace(id=a.state._user_id)
            return await call_next(request)

        yield c


@pytest_asyncio.fixture
async def client_other_user(tmp_path):
    """Client authenticated as a different user (u2) accessing u1's data."""
    a = _make_app(tmp_path, user_id="u2")
    db = a.state._db
    await db.connect()

    # Create test data owned by u1
    pid = await db.create_project("P", "", "u1")
    rid = await db.create_recording(pid, "a.wav", "/tmp/a.wav", "u1")
    sid = await db.create_speaker(rid, "SPEAKER_00", "Alice", "lv")
    seg_id = await db.create_segment(rid, sid, 0.0, 1.5, "Hello world")
    note_id = await db.create_note(seg_id, rid, "A note")
    a.state._test_rid = rid
    a.state._test_sid = sid
    a.state._test_seg_id = seg_id
    a.state._test_note_id = note_id

    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        @a.middleware("http")
        async def inject_user(request, call_next):
            request.state.user = SimpleNamespace(id="u2")
            return await call_next(request)

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
    app = client._transport.app  # type: ignore
    db_dep = app.dependency_overrides[get_db]
    db = await db_dep()

    rid = app.state._test_rid
    sid1 = app.state._test_sid  # Alice
    sid2 = await db.create_speaker(rid, "SPEAKER_01", "Bob", "lv")

    await db.create_segment(rid, sid1, 1.5, 3.0, "Alice says this")
    await db.create_segment(rid, sid2, 3.0, 5.0, "Bob says this")
    await db.create_segment(rid, sid2, 5.0, 7.0, "Bob says more")

    transcript = (await client.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
    assert len(transcript["speakers"]) == 2
    assert len(transcript["segments"]) == 4

    r = await client.post("/api/transcriber/speakers/merge",
                          json={"source_speaker_id": sid2, "target_speaker_id": sid1})
    assert r.status_code == 200
    assert r.json()["success"] is True

    transcript_after = (await client.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
    assert len(transcript_after["speakers"]) == 1
    assert transcript_after["speakers"][0]["id"] == sid1
    for seg in transcript_after["segments"]:
        assert seg["speaker_id"] == sid1


@pytest.mark.asyncio
async def test_merge_speakers_from_different_recordings_fails(client, tmp_path):
    app = client._transport.app  # type: ignore
    db_dep = app.dependency_overrides[get_db]
    db = await db_dep()

    rid1 = app.state._test_rid
    sid1 = app.state._test_sid

    pid = await db.create_project("P2", "", "u1")
    rid2 = await db.create_recording(pid, "b.wav", "/tmp/b.wav", "u1")
    sid2 = await db.create_speaker(rid2, "SPEAKER_00", "Charlie", "en")

    r = await client.post("/api/transcriber/speakers/merge",
                          json={"source_speaker_id": sid2, "target_speaker_id": sid1})
    assert r.status_code == 400
    assert "different recordings" in r.json()["detail"]


# ── Authorization tests (403 for other-user access) ───────────────────────────

@pytest.mark.asyncio
async def test_update_segment_forbidden_for_other_user(client_other_user):
    app = client_other_user._transport.app  # type: ignore
    seg_id = app.state._test_seg_id
    r = await client_other_user.patch(f"/api/transcriber/segments/{seg_id}", json={"text": "Hacked"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_speaker_forbidden_for_other_user(client_other_user):
    app = client_other_user._transport.app  # type: ignore
    sid = app.state._test_sid
    r = await client_other_user.patch(f"/api/transcriber/speakers/{sid}", json={"display_name": "Hacked"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_merge_speakers_forbidden_for_other_user(client_other_user):
    app = client_other_user._transport.app  # type: ignore
    db_dep = app.dependency_overrides[get_db]
    db = await db_dep()
    rid = app.state._test_rid
    sid1 = app.state._test_sid
    sid2 = await db.create_speaker(rid, "SPEAKER_01", "Bob", "lv")
    r = await client_other_user.post("/api/transcriber/speakers/merge",
                                     json={"source_speaker_id": sid2, "target_speaker_id": sid1})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_note_forbidden_for_other_user(client_other_user):
    app = client_other_user._transport.app  # type: ignore
    seg_id = app.state._test_seg_id
    rid = app.state._test_rid
    r = await client_other_user.post(f"/api/transcriber/segments/{seg_id}/notes",
                                     json={"content": "Hacked", "recording_id": rid})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_note_forbidden_for_other_user(client_other_user):
    app = client_other_user._transport.app  # type: ignore
    note_id = app.state._test_note_id
    r = await client_other_user.patch(f"/api/transcriber/notes/{note_id}", json={"content": "Hacked"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_note_forbidden_for_other_user(client_other_user):
    app = client_other_user._transport.app  # type: ignore
    note_id = app.state._test_note_id
    r = await client_other_user.delete(f"/api/transcriber/notes/{note_id}")
    assert r.status_code == 403


# ── Segment editing error cases ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_non_existent_segment_returns_404(client):
    r = await client.patch("/api/transcriber/segments/99999", json={"text": "Updated"})
    assert r.status_code == 404
    assert "Segment not found" in r.json()["detail"]


@pytest.mark.asyncio
async def test_update_segment_with_empty_text(client):
    rid = client._transport.app.state._test_rid  # type: ignore
    transcript = (await client.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
    seg_id = transcript["segments"][0]["id"]
    r = await client.patch(f"/api/transcriber/segments/{seg_id}", json={"text": ""})
    assert r.status_code == 200
    assert r.json()["text"] == ""
    assert r.json()["is_edited"] is True


@pytest.mark.asyncio
async def test_update_segment_with_text_over_5000_chars_fails(client):
    rid = client._transport.app.state._test_rid  # type: ignore
    transcript = (await client.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
    seg_id = transcript["segments"][0]["id"]
    long_text = "x" * 5001
    r = await client.patch(f"/api/transcriber/segments/{seg_id}", json={"text": long_text})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_original_text_preserved_after_edit(client):
    rid = client._transport.app.state._test_rid  # type: ignore
    transcript = (await client.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
    seg = transcript["segments"][0]
    seg_id = seg["id"]
    original = seg["text"]
    r = await client.patch(f"/api/transcriber/segments/{seg_id}", json={"text": "Edited"})
    assert r.status_code == 200
    updated_seg = r.json()
    assert updated_seg["text"] == "Edited"
    assert updated_seg["original_text"] == original
    assert updated_seg["is_edited"] is True


# ── Speaker operation error cases ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_non_existent_speaker_returns_404(client):
    r = await client.patch("/api/transcriber/speakers/99999", json={"display_name": "Ghost"})
    assert r.status_code == 404
    assert "Speaker not found" in r.json()["detail"]


@pytest.mark.asyncio
async def test_update_speaker_with_empty_display_name_fails(client):
    sid = client._transport.app.state._test_sid  # type: ignore
    r = await client.patch(f"/api/transcriber/speakers/{sid}", json={"display_name": ""})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_speaker_with_name_over_100_chars_fails(client):
    sid = client._transport.app.state._test_sid  # type: ignore
    long_name = "x" * 101
    r = await client.patch(f"/api/transcriber/speakers/{sid}", json={"display_name": long_name})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_merge_speaker_into_itself_fails(client):
    sid = client._transport.app.state._test_sid  # type: ignore
    r = await client.post("/api/transcriber/speakers/merge",
                          json={"source_speaker_id": sid, "target_speaker_id": sid})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_merge_non_existent_speakers_fails(client):
    r = await client.post("/api/transcriber/speakers/merge",
                          json={"source_speaker_id": 99999, "target_speaker_id": 99998})
    assert r.status_code == 404


# ── Note operation error cases ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_note_on_non_existent_segment_returns_404(client):
    rid = client._transport.app.state._test_rid  # type: ignore
    r = await client.post("/api/transcriber/segments/99999/notes",
                         json={"content": "Ghost note", "recording_id": rid})
    assert r.status_code == 404
    assert "Segment not found" in r.json()["detail"]


@pytest.mark.asyncio
async def test_update_note_happy_path(client):
    rid = client._transport.app.state._test_rid  # type: ignore
    transcript = (await client.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
    seg_id = transcript["segments"][0]["id"]
    r = await client.post(f"/api/transcriber/segments/{seg_id}/notes",
                         json={"content": "Original note", "recording_id": rid})
    assert r.status_code == 201
    note_id = r.json()["id"]
    r2 = await client.patch(f"/api/transcriber/notes/{note_id}", json={"content": "Updated note"})
    assert r2.status_code == 200
    assert r2.json()["content"] == "Updated note"


@pytest.mark.asyncio
async def test_update_non_existent_note_returns_404(client):
    r = await client.patch("/api/transcriber/notes/99999", json={"content": "Ghost"})
    assert r.status_code == 404
    assert "Note not found" in r.json()["detail"]


@pytest.mark.asyncio
async def test_delete_non_existent_note_returns_404(client):
    r = await client.delete("/api/transcriber/notes/99999")
    assert r.status_code == 404
    assert "Note not found" in r.json()["detail"]


@pytest.mark.asyncio
async def test_create_note_with_content_over_2000_chars_fails(client):
    rid = client._transport.app.state._test_rid  # type: ignore
    transcript = (await client.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
    seg_id = transcript["segments"][0]["id"]
    long_content = "x" * 2001
    r = await client.post(f"/api/transcriber/segments/{seg_id}/notes",
                         json={"content": long_content, "recording_id": rid})
    assert r.status_code == 422


# ── Transcript retrieval error cases ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_transcript_for_non_existent_recording_returns_404(client):
    r = await client.get("/api/transcriber/recordings/99999/transcript")
    assert r.status_code == 404
    assert "Recording not found" in r.json()["detail"]


@pytest.mark.asyncio
async def test_get_transcript_with_no_segments(client, tmp_path):
    app = client._transport.app  # type: ignore
    db_dep = app.dependency_overrides[get_db]
    db = await db_dep()
    pid = await db.create_project("Empty Project", "", "u1")
    rid = await db.create_recording(pid, "empty.wav", "/tmp/empty.wav", "u1")
    r = await client.get(f"/api/transcriber/recordings/{rid}/transcript")
    assert r.status_code == 200
    data = r.json()
    assert len(data["segments"]) == 0
    assert len(data["speakers"]) == 0
    assert data["recording"]["id"] == rid
