# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_orchestrator.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for TranscriberOrchestrator (GH#10128).

No real audio, ffmpeg, or ML runs.  All heavy dependencies are mocked.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import RecordingStatus
from transcriber.orchestrator import TranscriberOrchestrator, _assign_speaker
from transcriber.routes.projects import router as projects_router
from transcriber.routes.recordings import router as recordings_router
from voice_processing.providers import TranscriptSegment

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db(tmp_path):
    """Bare transcriber database connected to a temp file."""
    _db = Database(str(tmp_path / "test.db"))
    await _db.connect()
    yield _db
    await _db.close()


@pytest_asyncio.fixture
async def client(tmp_path):
    """Full ASGI client with DB and upload dir wired in."""
    app = FastAPI()
    _db = Database(str(tmp_path / "test.db"))
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    async def override_db():
        return _db

    await _db.connect()
    app.dependency_overrides[get_db] = override_db
    app.state.transcriber_upload_dir = str(upload_dir)
    app.include_router(projects_router, prefix="/api/transcriber")
    app.include_router(recordings_router, prefix="/api/transcriber")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── helper ────────────────────────────────────────────────────────────────────


async def _make_recording(db: Database, tmp_path, status: str = "pending") -> int:
    """Insert a project + recording row; write a dummy file; return recording id."""
    pid = await db.create_project("TestProject", "", "user1")
    filepath = str(tmp_path / "audio.wav")
    with open(filepath, "wb") as f:
        f.write(b"\x00" * 64)
    rid = await db.create_recording(pid, "audio.wav", filepath, "user1")
    if status != "pending":
        await db.update_recording_status(rid, status)
    return rid


# ── unit tests: _assign_speaker ───────────────────────────────────────────────


def test_assign_speaker_no_diar_returns_speaker_00():
    seg = TranscriptSegment(text="hi", start_time=0.0, end_time=1.0, confidence=1.0)
    assert _assign_speaker(seg, []) == "SPEAKER_00"


def test_assign_speaker_picks_max_overlap():
    from media.audio.diarization_service import SpeakerSegment

    seg = TranscriptSegment(text="hello", start_time=1.0, end_time=3.0, confidence=1.0)
    diar = [
        SpeakerSegment("SPEAKER_00", 0.0, 1.5),  # overlap = 0.5
        SpeakerSegment("SPEAKER_01", 1.5, 4.0),  # overlap = 1.5
    ]
    assert _assign_speaker(seg, diar) == "SPEAKER_01"


# ── orchestrator happy path ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_recording_happy_path(db, tmp_path):
    from media.audio.diarization_service import SpeakerSegment

    rid = await _make_recording(db, tmp_path)

    diar_segments = [
        SpeakerSegment("SPEAKER_00", 0.0, 2.0),
        SpeakerSegment("SPEAKER_01", 2.0, 4.0),
    ]
    transcript_segments = [
        TranscriptSegment(text="Hello world", start_time=0.0, end_time=2.0, confidence=0.9),
        TranscriptSegment(text="Goodbye", start_time=2.5, end_time=4.0, confidence=0.85),
    ]

    mock_ffmpeg = MagicMock()
    mock_ffmpeg.extract_audio = AsyncMock(return_value=None)
    mock_ffmpeg.get_audio_duration = AsyncMock(return_value=4.0)

    mock_diar = MagicMock()
    mock_diar.diarize = AsyncMock(return_value=diar_segments)

    mock_provider = MagicMock()
    mock_provider.provider_name = "mock_provider"
    mock_provider.transcribe = AsyncMock(return_value=transcript_segments)

    mock_registry = MagicMock()
    mock_registry.get_provider = MagicMock(return_value=mock_provider)

    orch = TranscriberOrchestrator(db=db)
    orch.ffmpeg_service = mock_ffmpeg
    orch.diarization_service = mock_diar
    orch.provider_registry = mock_registry

    with (
        patch("transcriber.orchestrator.is_diarization_available", return_value=True),
        patch("transcriber.orchestrator.detect_language", new=AsyncMock(return_value="en")),
        patch("transcriber.orchestrator._validate_file_path"),
    ):
        result = await orch.process_recording(rid)

    assert result["status"] == RecordingStatus.COMPLETE.value
    assert result["segments_count"] == 2

    # Speaker rows created
    speakers = await db.list_speakers(rid)
    speaker_labels = {s["label"] for s in speakers}
    assert "SPEAKER_00" in speaker_labels
    assert "SPEAKER_01" in speaker_labels

    # Segments persisted with correct speaker assignment
    segments = await db.list_segments(rid)
    assert len(segments) == 2
    sp00_id = next(s["id"] for s in speakers if s["label"] == "SPEAKER_00")
    sp01_id = next(s["id"] for s in speakers if s["label"] == "SPEAKER_01")
    assert segments[0]["speaker_id"] == sp00_id
    assert segments[1]["speaker_id"] == sp01_id

    # Final DB status
    rec = await db.get_recording(rid)
    assert rec["status"] == RecordingStatus.COMPLETE.value
    assert rec["speaker_count"] == 2
    assert rec["language_detected"] == "en"


# ── single-speaker fallback ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_recording_single_speaker_fallback(db, tmp_path):
    rid = await _make_recording(db, tmp_path)

    transcript_segments = [
        TranscriptSegment(text="Only speaker", start_time=0.0, end_time=3.0, confidence=0.95),
    ]

    mock_ffmpeg = MagicMock()
    mock_ffmpeg.extract_audio = AsyncMock(return_value=None)
    mock_ffmpeg.get_audio_duration = AsyncMock(return_value=3.0)

    mock_provider = MagicMock()
    mock_provider.provider_name = "mock_provider"
    mock_provider.transcribe = AsyncMock(return_value=transcript_segments)

    mock_registry = MagicMock()
    mock_registry.get_provider = MagicMock(return_value=mock_provider)

    orch = TranscriberOrchestrator(db=db)
    orch.ffmpeg_service = mock_ffmpeg
    orch.provider_registry = mock_registry

    with (
        patch("transcriber.orchestrator.is_diarization_available", return_value=False),
        patch("transcriber.orchestrator.detect_language", new=AsyncMock(return_value="en")),
        patch("transcriber.orchestrator._validate_file_path"),
    ):
        result = await orch.process_recording(rid)

    assert result["status"] == RecordingStatus.COMPLETE.value
    speakers = await db.list_speakers(rid)
    assert len(speakers) == 1
    assert speakers[0]["label"] == "SPEAKER_00"
    segments = await db.list_segments(rid)
    assert len(segments) == 1
    assert segments[0]["text"] == "Only speaker"


# ── failure path ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_recording_failure_sets_error_status(db, tmp_path):
    rid = await _make_recording(db, tmp_path)

    mock_ffmpeg = MagicMock()
    mock_ffmpeg.extract_audio = AsyncMock(side_effect=RuntimeError("ffmpeg not found"))
    mock_ffmpeg.get_audio_duration = AsyncMock(return_value=0.0)

    orch = TranscriberOrchestrator(db=db)
    orch.ffmpeg_service = mock_ffmpeg

    with (patch("transcriber.orchestrator._validate_file_path"),):
        with pytest.raises(RuntimeError, match="ffmpeg not found"):
            await orch.process_recording(rid)

    rec = await db.get_recording(rid)
    assert rec["status"] == RecordingStatus.ERROR.value
    assert rec["failure_stage"] == "RuntimeError"
    assert rec["failure_reason"] is not None


# ── upload route enqueues task ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_enqueues_transcription_task(client):
    r = await client.post("/api/transcriber/projects", json={"name": "P", "description": ""})
    pid = r.json()["id"]
    audio_bytes = b"RIFF" + b"\x00" * 100

    mock_task = MagicMock()
    mock_delay = MagicMock()
    mock_task.delay = mock_delay

    # The route uses a deferred `from tasks.transcriber_tasks import transcribe_recording`
    # inside the request handler to avoid circular imports, so we patch the source module.
    with patch("tasks.transcriber_tasks.transcribe_recording", mock_task):
        r2 = await client.post(
            f"/api/transcriber/projects/{pid}/recordings",
            files={"file": ("test.wav", io.BytesIO(audio_bytes), "audio/wav")},
        )

    assert r2.status_code == 202
    assert r2.json()["status"] == "pending"
    mock_delay.assert_called_once()
    called_rid = mock_delay.call_args[0][0]
    assert isinstance(called_rid, int)
