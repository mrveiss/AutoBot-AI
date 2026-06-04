"""Tests for transcript export base classes and data models."""

from services.transcript_export.base import Segment, Transcript


def test_segment_creation():
    """Test Segment model creation."""
    segment = Segment(
        id="seg-1",
        transcript_id="trans-1",
        start_time=5.0,
        end_time=10.5,
        speaker_label="Speaker 1",
        text="Hello world",
    )
    assert segment.start_time == 5.0
    assert segment.end_time == 10.5
    assert segment.speaker_label == "Speaker 1"
    assert segment.text == "Hello world"


def test_segment_duration():
    """Test segment duration calculation."""
    segment = Segment(
        id="seg-1",
        transcript_id="trans-1",
        start_time=5.0,
        end_time=10.5,
        speaker_label="Speaker 1",
        text="Hello world",
    )
    assert segment.duration == 5.5


def test_transcript_creation():
    """Test Transcript model creation with segments."""
    segments = [
        Segment(
            id="seg-1",
            transcript_id="trans-1",
            start_time=0.0,
            end_time=5.0,
            speaker_label="Speaker 1",
            text="First segment",
        ),
        Segment(
            id="seg-2",
            transcript_id="trans-1",
            start_time=5.0,
            end_time=10.0,
            speaker_label="Speaker 2",
            text="Second segment",
        ),
    ]

    transcript = Transcript(
        id="trans-1",
        title="Test Transcript",
        duration_seconds=10.0,
        language="en",
        segments=segments,
    )

    assert transcript.id == "trans-1"
    assert transcript.title == "Test Transcript"
    assert len(transcript.segments) == 2
    assert transcript.segments[0].speaker_label == "Speaker 1"
