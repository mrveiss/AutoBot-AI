"""Tests for SRT (SubRip) subtitle exporter."""

import pytest
from services.transcript_export.base import Segment, Transcript
from services.transcript_export.srt_exporter import SRTExporter


@pytest.fixture
def sample_transcript():
    """Sample transcript for testing."""
    return Transcript(
        id="test-123",
        title="Test Meeting",
        duration_seconds=30.0,
        language="en",
        segments=[
            Segment(
                id="seg-1",
                transcript_id="test-123",
                start_time=5.0,
                end_time=10.0,
                speaker_label="Speaker 1",
                text="Hello everyone, welcome to the meeting.",
            ),
            Segment(
                id="seg-2",
                transcript_id="test-123",
                start_time=12.5,
                end_time=18.0,
                speaker_label="Speaker 2",
                text="Thank you for having us.",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_srt_generate(sample_transcript):
    """Test SRT generation with proper formatting."""
    exporter = SRTExporter(sample_transcript)
    result = await exporter.generate()

    # Decode bytes to string
    content = result.decode("utf-8")

    # Check SRT structure
    assert "1\n" in content  # First sequence number
    assert "00:00:05,000 --> 00:00:10,000" in content  # First timestamp
    assert "Speaker 1: Hello everyone, welcome to the meeting." in content

    assert "2\n" in content  # Second sequence number
    assert "00:00:12,500 --> 00:00:18,000" in content  # Second timestamp
    assert "Speaker 2: Thank you for having us." in content


@pytest.mark.asyncio
async def test_srt_mime_type():
    """Test SRT MIME type."""
    transcript = Transcript(
        id="test",
        title="Test",
        duration_seconds=10.0,
        language="en",
        segments=[],
    )
    exporter = SRTExporter(transcript)
    assert exporter.get_mime_type() == "application/x-subrip"


@pytest.mark.asyncio
async def test_srt_file_extension():
    """Test SRT file extension."""
    transcript = Transcript(
        id="test",
        title="Test",
        duration_seconds=10.0,
        language="en",
        segments=[],
    )
    exporter = SRTExporter(transcript)
    assert exporter.get_file_extension() == ".srt"


@pytest.mark.asyncio
async def test_srt_empty_segments():
    """Test SRT generation with no segments."""
    transcript = Transcript(
        id="test",
        title="Empty Transcript",
        duration_seconds=0.0,
        language="en",
        segments=[],
    )
    exporter = SRTExporter(transcript)
    result = await exporter.generate()
    content = result.decode("utf-8")

    # Should be empty or minimal
    assert len(content.strip()) == 0
