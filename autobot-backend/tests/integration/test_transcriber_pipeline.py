# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Transcriber Pipeline Integration Test
# Issue #9044, MVA-2186 — rewritten for the canonical API (#11648):
# the original targeted a retired contract (TranscriberDatabase with
# ``initialize()``/object rows, RecordingStatus.COMPLETED/FAILED,
# orchestrator._merge_segments). Canonical surface: ``transcriber.database.
# Database`` (dict rows, project-scoped recordings), RecordingStatus
# ``complete``/``error``, and time-overlap merging inside the orchestrator's
# persist helpers.

"""Integration test for the transcriber pipeline services and database."""

import pytest
import pytest_asyncio

from media.audio.diarization_service import get_diarization_service
from media.audio.ffmpeg_service import get_ffmpeg_service
from transcriber.database import Database
from transcriber.models import RecordingStatus
from transcriber.orchestrator import TranscriberOrchestrator
from voice_processing.language_detection import detect_language
from voice_processing.providers import get_speech_provider_registry


@pytest_asyncio.fixture
async def transcriber_db(tmp_path):
    """Create a connected test database backed by a temp file."""
    db = Database(str(tmp_path / "transcriber-test.db"))
    await db.connect()
    yield db
    await db.close()


@pytest_asyncio.fixture
async def project_id(transcriber_db):
    """Create a project to attach recordings to."""
    return await transcriber_db.create_project("Pipeline Test", "integration", user_id="u1")


@pytest.fixture
def orchestrator(transcriber_db):
    """Create orchestrator with test database."""
    return TranscriberOrchestrator(db=transcriber_db)


@pytest.mark.asyncio
async def test_service_availability():
    """All pipeline services must be importable and constructible."""
    assert get_ffmpeg_service() is not None
    assert get_diarization_service() is not None
    assert get_speech_provider_registry() is not None

    # Language detection degrades to None for a missing audio file.
    result = await detect_language(audio_path="/nonexistent/sample_lv.wav", filename_hint="sample_lv.wav")
    assert result in ["lv", "en", None]


@pytest.mark.asyncio
async def test_database_operations(transcriber_db, project_id):
    """Database create/read/update round-trip via the canonical API."""
    recording_id = await transcriber_db.create_recording(
        project_id, "test.wav", "/tmp/test.wav", user_id="u1"
    )
    assert recording_id > 0

    recording = await transcriber_db.get_recording(recording_id)
    assert recording is not None
    assert recording["filename"] == "test.wav"
    assert recording["status"] == RecordingStatus.PENDING.value

    await transcriber_db.update_recording_status(
        recording_id,
        RecordingStatus.COMPLETE.value,
        language_detected="lv",
        speaker_count=2,
        process_seconds=10.5,
    )
    await transcriber_db.update_recording_duration(recording_id, 42.0)

    updated = await transcriber_db.get_recording(recording_id)
    assert updated["status"] == RecordingStatus.COMPLETE.value
    assert updated["language_detected"] == "lv"
    assert updated["speaker_count"] == 2
    assert updated["duration"] == 42.0


@pytest.mark.asyncio
async def test_segment_creation(transcriber_db, project_id):
    """Speaker + segment creation and time-ordered retrieval."""
    recording_id = await transcriber_db.create_recording(
        project_id, "test.wav", "/tmp/test.wav", user_id="u1"
    )

    speaker_a = await transcriber_db.create_speaker(recording_id, "SPEAKER_00", "Speaker 1", "lv")
    speaker_b = await transcriber_db.create_speaker(recording_id, "SPEAKER_01", "Speaker 2", "lv")

    await transcriber_db.create_segment(recording_id, speaker_b, 2.5, 5.0, "Testing transcription")
    await transcriber_db.create_segment(recording_id, speaker_a, 0.0, 2.5, "Hello world")

    segments = await transcriber_db.list_segments(recording_id)
    assert len(segments) == 2
    # list_segments orders by start_time regardless of insertion order
    assert segments[0]["start_time"] < segments[1]["start_time"]
    assert segments[0]["speaker_id"] == speaker_a
    assert segments[1]["speaker_id"] == speaker_b
    assert segments[0]["text"] == "Hello world"

    speakers = await transcriber_db.list_speakers(recording_id)
    assert {s["label"] for s in speakers} == {"SPEAKER_00", "SPEAKER_01"}


@pytest.mark.asyncio
async def test_process_recording_unknown_id_raises(orchestrator):
    """Processing a nonexistent recording must raise, not silently pass."""
    with pytest.raises(ValueError, match="not found"):
        await orchestrator.process_recording(999999)


@pytest.mark.asyncio
async def test_process_recording_rejects_non_pending(orchestrator, transcriber_db, project_id):
    """Only pending recordings may enter the pipeline (double-run guard)."""
    recording_id = await transcriber_db.create_recording(
        project_id, "done.wav", "/tmp/done.wav", user_id="u1"
    )
    await transcriber_db.update_recording_status(recording_id, RecordingStatus.COMPLETE.value)

    with pytest.raises(ValueError, match="not pending"):
        await orchestrator.process_recording(recording_id)


@pytest.mark.asyncio
async def test_process_recording_blocks_path_outside_upload_dir(
    orchestrator, transcriber_db, project_id, tmp_path, monkeypatch
):
    """Issue #9214: files outside the upload base dir must be rejected."""
    monkeypatch.setenv("AUTOBOT_UPLOAD_DIR", str(tmp_path / "uploads"))
    recording_id = await transcriber_db.create_recording(
        project_id, "invalid.wav", "/nonexistent/path.wav", user_id="u1"
    )

    with pytest.raises(ValueError):
        await orchestrator.process_recording(recording_id)

    # Validation failure is a caller error: the recording stays pending.
    recording = await transcriber_db.get_recording(recording_id)
    assert recording["status"] == RecordingStatus.PENDING.value
