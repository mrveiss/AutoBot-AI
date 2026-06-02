# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Transcriber Pipeline Integration Test
# Issue #9044, MVA-2186

"""Integration test for transcriber pipeline with sample audio."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from media.audio.diarization_service import get_diarization_service
from media.audio.ffmpeg_service import get_ffmpeg_service
from transcriber.database import TranscriberDatabase
from transcriber.models import RecordingStatus
from transcriber.orchestrator import TranscriberOrchestrator
from voice_processing.language_detection import detect_language
from voice_processing.providers import get_provider_registry


@pytest.fixture
async def transcriber_db():
    """Create a test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = TranscriberDatabase(db_path)
    await db.initialize()
    yield db

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def orchestrator(transcriber_db):
    """Create orchestrator with test database."""
    return TranscriberOrchestrator(db=transcriber_db)


@pytest.fixture
def sample_audio_path():
    """Path to a sample audio file for testing.

    NOTE: For actual testing, you would provide a real audio file path here.
    This is a placeholder that should be replaced with actual test audio.
    """
    # For testing, we'll create a minimal WAV file
    # In production, use a real test audio file with Latvian + English content
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        # Minimal WAV header (44 bytes) + 1 second of silence
        wav_header = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        silence = b"\x00" * 16000  # 1 second of silence at 16kHz
        tmp.write(wav_header)
        tmp.write(silence)
        tmp_path = tmp.name

    yield tmp_path

    # Cleanup
    Path(tmp_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_service_availability():
    """Test that all required services are available."""
    # FFmpeg service
    ffmpeg = get_ffmpeg_service()
    assert ffmpeg is not None

    # Diarization service
    diarization = get_diarization_service()
    assert diarization is not None

    # Speech provider registry
    registry = get_provider_registry()
    assert registry is not None

    # Check that language detection works
    # (This will use filename hints since the sample is minimal)
    result = await detect_language(audio_path=None, filename_hint="sample_lv.wav")
    assert result in ["lv", "en", None]  # Should return a valid language code or None


@pytest.mark.asyncio
async def test_database_operations(transcriber_db):
    """Test database create/read operations."""
    # Create recording
    recording = await transcriber_db.create_recording(filename="test.wav", file_path="/tmp/test.wav")

    assert recording.id > 0
    assert recording.filename == "test.wav"
    assert recording.status == RecordingStatus.PENDING

    # Get recording
    retrieved = await transcriber_db.get_recording(recording.id)
    assert retrieved is not None
    assert retrieved.id == recording.id

    # Update status
    await transcriber_db.update_recording_status(recording.id, RecordingStatus.COMPLETED, duration=10.5, language="lv")

    updated = await transcriber_db.get_recording(recording.id)
    assert updated.status == RecordingStatus.COMPLETED
    assert updated.duration == 10.5
    assert updated.language == "lv"


@pytest.mark.asyncio
async def test_segment_creation(transcriber_db):
    """Test segment creation and retrieval."""
    # Create recording first
    recording = await transcriber_db.create_recording(filename="test.wav", file_path="/tmp/test.wav")

    # Create segments
    segments_data = [
        {
            "speaker_label": "SPEAKER_00",
            "start_time": 0.0,
            "end_time": 2.5,
            "text": "Hello world",
            "confidence": 0.95,
        },
        {
            "speaker_label": "SPEAKER_01",
            "start_time": 2.5,
            "end_time": 5.0,
            "text": "Testing transcription",
            "confidence": 0.92,
        },
    ]

    created_segments = await transcriber_db.create_segments(segments=segments_data, recording_id=recording.id)

    assert len(created_segments) == 2
    assert created_segments[0].speaker_label == "SPEAKER_00"
    assert created_segments[1].speaker_label == "SPEAKER_01"

    # Retrieve segments
    retrieved_segments = await transcriber_db.get_recording_segments(recording.id)
    assert len(retrieved_segments) == 2
    assert retrieved_segments[0].start_time < retrieved_segments[1].start_time


@pytest.mark.asyncio
async def test_merge_segments_logic(orchestrator):
    """Test the segment merging algorithm."""
    # Mock speaker segments
    from media.audio.diarization_service import SpeakerSegment

    speaker_segments = [
        SpeakerSegment(speaker="SPEAKER_00", start=0.0, end=2.0),
        SpeakerSegment(speaker="SPEAKER_01", start=2.0, end=4.0),
        SpeakerSegment(speaker="SPEAKER_00", start=4.0, end=6.0),
    ]

    transcription_text = "This is the first segment. This is the second segment. This is the third segment."

    merged = orchestrator._merge_segments(
        speaker_segments=speaker_segments,
        transcription_text=transcription_text,
        confidence=0.95,
    )

    assert len(merged) == 3
    assert merged[0]["speaker_label"] == "SPEAKER_00"
    assert merged[1]["speaker_label"] == "SPEAKER_01"
    assert merged[2]["speaker_label"] == "SPEAKER_00"

    # Each segment should have some text
    assert len(merged[0]["text"]) > 0
    assert len(merged[1]["text"]) > 0
    assert len(merged[2]["text"]) > 0

    # All segments together should contain all words
    all_text = " ".join(seg["text"] for seg in merged)
    assert len(all_text.split()) == len(transcription_text.split())


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires real audio file with speech content")
async def test_full_pipeline_integration(orchestrator, transcriber_db, sample_audio_path):
    """Integration test for the full transcription pipeline.

    NOTE: This test is skipped by default because it requires:
    1. A real audio file with actual speech content
    2. FFmpeg installed
    3. Pyannote model available (optional, will skip diarization if unavailable)
    4. Speech provider configured

    To run this test:
    1. Replace sample_audio_path fixture with path to real audio
    2. Ensure all dependencies are installed
    3. Remove the @pytest.mark.skip decorator
    """
    # Create recording entry
    recording = await transcriber_db.create_recording(filename="integration_test.wav", file_path=sample_audio_path)

    # Process through pipeline
    result = await orchestrator.process_recording(recording.id)

    # Verify results
    assert result["recording_id"] == recording.id
    assert result["status"] == RecordingStatus.COMPLETED.value
    assert result["segments_count"] > 0

    # Verify recording was updated
    updated_recording = await transcriber_db.get_recording(recording.id)
    assert updated_recording.status == RecordingStatus.COMPLETED
    assert updated_recording.duration is not None
    assert updated_recording.language is not None

    # Verify segments were created
    segments = await transcriber_db.get_recording_segments(recording.id)
    assert len(segments) > 0
    assert segments[0].text != ""
    assert segments[0].confidence > 0


@pytest.mark.asyncio
async def test_processing_error_handling(orchestrator, transcriber_db):
    """Test error handling when processing fails."""
    # Create recording with invalid file path
    recording = await transcriber_db.create_recording(filename="invalid.wav", file_path="/nonexistent/path.wav")

    # Processing should fail and mark recording as failed
    with pytest.raises(Exception):
        await orchestrator.process_recording(recording.id)

    # Verify status was updated to failed
    failed_recording = await transcriber_db.get_recording(recording.id)
    assert failed_recording.status == RecordingStatus.FAILED


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
