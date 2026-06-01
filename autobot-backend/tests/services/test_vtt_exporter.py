"""Tests for VTT (WebVTT) subtitle exporter."""
import pytest
from services.transcript_export.base import Segment, Transcript
from services.transcript_export.vtt_exporter import VTTExporter


@pytest.fixture
def sample_transcript():
    """Sample transcript for testing."""
    return Transcript(
        id="test-456",
        title="Test Webinar",
        duration_seconds=25.0,
        language="en",
        segments=[
            Segment(
                id="seg-1",
                transcript_id="test-456",
                start_time=3.5,
                end_time=8.0,
                speaker_label="John Doe",
                text="Welcome to our webinar.",
            ),
            Segment(
                id="seg-2",
                transcript_id="test-456",
                start_time=10.0,
                end_time=15.5,
                speaker_label="Jane Smith",
                text="Let's begin with the first topic.",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_vtt_generate(sample_transcript):
    """Test VTT generation with proper formatting."""
    exporter = VTTExporter(sample_transcript)
    result = await exporter.generate()

    content = result.decode("utf-8")

    # Check VTT header
    assert content.startswith("WEBVTT")

    # Check timestamps (dots not commas)
    assert "00:00:03.500 --> 00:00:08.000" in content
    assert "00:00:10.000 --> 00:00:15.500" in content

    # Check voice tags
    assert "<v John Doe>" in content
    assert "Welcome to our webinar." in content
    assert "<v Jane Smith>" in content
    assert "Let's begin with the first topic." in content


@pytest.mark.asyncio
async def test_vtt_mime_type():
    """Test VTT MIME type."""
    transcript = Transcript(
        id="test",
        title="Test",
        duration_seconds=10.0,
        language="en",
        segments=[],
    )
    exporter = VTTExporter(transcript)
    assert exporter.get_mime_type() == "text/vtt"


@pytest.mark.asyncio
async def test_vtt_file_extension():
    """Test VTT file extension."""
    transcript = Transcript(
        id="test",
        title="Test",
        duration_seconds=10.0,
        language="en",
        segments=[],
    )
    exporter = VTTExporter(transcript)
    assert exporter.get_file_extension() == ".vtt"


@pytest.mark.asyncio
async def test_vtt_empty_segments():
    """Test VTT generation with no segments."""
    transcript = Transcript(
        id="test",
        title="Empty",
        duration_seconds=0.0,
        language="en",
        segments=[],
    )
    exporter = VTTExporter(transcript)
    result = await exporter.generate()
    content = result.decode("utf-8")

    # Should still have WEBVTT header
    assert content.strip() == "WEBVTT"
