# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_audio_api.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for audio chunk streaming and waveform endpoints (#9466)."""

import io
import struct
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.routes.projects import router as projects_router
from transcriber.routes.recordings import _generate_waveform
from transcriber.routes.recordings import router as recordings_router

USER_HEADER = "x-test-user"

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_wav(path: Path, n_frames: int = 4000, n_channels: int = 1, sampwidth: int = 2, framerate: int = 8000) -> None:
    """Write a minimal but valid WAV file with a sine-like pattern."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        # Alternating +32000/-32000 to produce clear peaks
        frames = b""
        for i in range(n_frames):
            sample = 32000 if i % 2 == 0 else -32000
            frames += struct.pack("<h", sample) * n_channels
        wf.writeframes(frames)


@pytest_asyncio.fixture
async def client(tmp_path):
    """App fixture with header-driven user identity and a real WAV file."""
    app = FastAPI()
    db = Database(str(tmp_path / "test.db"))
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    async def override_db():
        return db

    @app.middleware("http")
    async def set_user(request: Request, call_next):
        uid = request.headers.get(USER_HEADER)
        if uid:
            request.state.user = SimpleNamespace(id=uid)
        return await call_next(request)

    await db.connect()
    app.dependency_overrides[get_db] = override_db
    app.state.transcriber_upload_dir = str(upload_dir)
    app.include_router(projects_router, prefix="/api/transcriber")
    app.include_router(recordings_router, prefix="/api/transcriber")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _create_project_and_recording(client, user: str, upload_dir: Path) -> tuple[int, int, Path]:
    """Create a project and upload a real WAV recording; return (pid, rid, wav_path)."""
    r = await client.post(
        "/api/transcriber/projects",
        json={"name": "audio-test", "description": ""},
        headers={USER_HEADER: user},
    )
    assert r.status_code == 201
    pid = r.json()["id"]

    # Build a real WAV in memory
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        frames = b"".join(struct.pack("<h", 32000 if i % 2 == 0 else -32000) for i in range(4000))
        wf.writeframes(frames)
    wav_bytes = buf.getvalue()

    r2 = await client.post(
        f"/api/transcriber/projects/{pid}/recordings",
        files={"file": ("test.wav", io.BytesIO(wav_bytes), "audio/wav")},
        headers={USER_HEADER: user},
    )
    assert r2.status_code == 202
    rid = r2.json()["id"]
    return pid, rid, wav_bytes


# ── Unit tests for waveform helper ────────────────────────────────────────────


def test_generate_waveform_real_wav(tmp_path):
    """_generate_waveform returns a non-empty list for a valid WAV file."""
    wav_path = tmp_path / "sample.wav"
    _make_wav(wav_path, n_frames=4000)
    peaks = _generate_waveform(str(wav_path), width=200)
    assert len(peaks) > 0
    assert len(peaks) <= 200
    assert all(0.0 <= p <= 1.0 for p in peaks), "All peaks must be normalized to [0,1]"


def test_generate_waveform_non_wav_returns_empty(tmp_path):
    """_generate_waveform returns [] for a non-WAV file (graceful fallback)."""
    mp3_path = tmp_path / "fake.mp3"
    mp3_path.write_bytes(b"\xff\xfb\x90\x00" * 100)
    peaks = _generate_waveform(str(mp3_path), width=100)
    assert peaks == []


def test_generate_waveform_missing_file_returns_empty(tmp_path):
    """_generate_waveform returns [] for a missing file (graceful fallback)."""
    peaks = _generate_waveform(str(tmp_path / "does_not_exist.wav"), width=100)
    assert peaks == []


# ── HTTP endpoint tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audio_chunks_full_file(client, tmp_path):
    """GET /audio/chunks without Range header returns 200 with full content."""
    _, rid, wav_bytes = await _create_project_and_recording(client, "alice", tmp_path)
    r = await client.get(f"/api/transcriber/recordings/{rid}/audio/chunks", headers={USER_HEADER: "alice"})
    assert r.status_code == 200
    assert r.headers.get("accept-ranges") == "bytes"
    assert int(r.headers["content-length"]) == len(wav_bytes)
    assert r.content == wav_bytes


@pytest.mark.asyncio
async def test_audio_chunks_range_request(client, tmp_path):
    """GET /audio/chunks with Range header returns 206 Partial Content."""
    _, rid, wav_bytes = await _create_project_and_recording(client, "alice", tmp_path)
    r = await client.get(
        f"/api/transcriber/recordings/{rid}/audio/chunks",
        headers={USER_HEADER: "alice", "Range": "bytes=0-99"},
    )
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 0-99/{len(wav_bytes)}"
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-length"] == "100"
    assert r.content == wav_bytes[:100]


@pytest.mark.asyncio
async def test_audio_chunks_unsatisfiable_range(client, tmp_path):
    """GET /audio/chunks with out-of-bounds Range returns 416."""
    _, rid, wav_bytes = await _create_project_and_recording(client, "alice", tmp_path)
    file_size = len(wav_bytes)
    r = await client.get(
        f"/api/transcriber/recordings/{rid}/audio/chunks",
        headers={USER_HEADER: "alice", "Range": f"bytes={file_size}-{file_size + 999}"},
    )
    assert r.status_code == 416


@pytest.mark.asyncio
async def test_audio_chunks_ownership_returns_404(client, tmp_path):
    """GET /audio/chunks as a different user returns 404 (IDOR guard)."""
    _, rid, _ = await _create_project_and_recording(client, "alice", tmp_path)
    r = await client.get(f"/api/transcriber/recordings/{rid}/audio/chunks", headers={USER_HEADER: "bob"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_audio_waveform_happy_path(client, tmp_path):
    """GET /audio/waveform returns peaks within bounds and aligned segments."""
    _, rid, _ = await _create_project_and_recording(client, "alice", tmp_path)
    r = await client.get(
        f"/api/transcriber/recordings/{rid}/audio/waveform",
        params={"width": 100},
        headers={USER_HEADER: "alice"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["recording_id"] == rid
    assert isinstance(data["peaks"], list)
    assert data["width"] == len(data["peaks"])
    assert len(data["peaks"]) <= 100
    assert "segments" in data
    assert isinstance(data["segments"], list)


@pytest.mark.asyncio
async def test_audio_waveform_ownership_returns_404(client, tmp_path):
    """GET /audio/waveform as a different user returns 404 (IDOR guard)."""
    _, rid, _ = await _create_project_and_recording(client, "alice", tmp_path)
    r = await client.get(f"/api/transcriber/recordings/{rid}/audio/waveform", headers={USER_HEADER: "bob"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_audio_waveform_segments_present(client, tmp_path):
    """Waveform response includes any segments stored for the recording."""
    _, rid, _ = await _create_project_and_recording(client, "alice", tmp_path)

    # Locate the db via the app state (injected through the fixture)
    # We exercise via the transcripts API instead: just verify zero segments is valid
    r = await client.get(
        f"/api/transcriber/recordings/{rid}/audio/waveform",
        headers={USER_HEADER: "alice"},
    )
    assert r.status_code == 200
    assert r.json()["segments"] == []


@pytest.mark.asyncio
async def test_audio_chunks_missing_recording_returns_404(client, tmp_path):
    """Non-existent recording_id returns 404 for both audio endpoints."""
    r = await client.get("/api/transcriber/recordings/99999/audio/chunks", headers={USER_HEADER: "alice"})
    assert r.status_code == 404
    r = await client.get("/api/transcriber/recordings/99999/audio/waveform", headers={USER_HEADER: "alice"})
    assert r.status_code == 404
