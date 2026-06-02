# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Diarization Service Tests
# Issue #9044: Speaker diarization tests

"""Tests for Pyannote speaker diarization service."""

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from media.audio.diarization_service import (
    DiarizationService,
    SpeakerSegment,
    get_diarization_service,
    is_diarization_available,
)


class TestSpeakerSegment:
    """Test SpeakerSegment data class."""

    def test_speaker_segment_creation(self):
        """Test creating a speaker segment."""
        segment = SpeakerSegment("SPEAKER_00", 0.0, 5.5)

        assert segment.speaker_label == "SPEAKER_00"
        assert segment.start_time == 0.0
        assert segment.end_time == 5.5

    def test_speaker_segment_to_tuple(self):
        """Test converting segment to tuple."""
        segment = SpeakerSegment("SPEAKER_01", 10.2, 15.8)
        result = segment.to_tuple()

        assert result == ("SPEAKER_01", 10.2, 15.8)
        assert isinstance(result, tuple)

    def test_speaker_segment_to_dict(self):
        """Test converting segment to dictionary."""
        segment = SpeakerSegment("SPEAKER_02", 20.0, 30.5)
        result = segment.to_dict()

        assert result == {
            "speaker_label": "SPEAKER_02",
            "start_time": 20.0,
            "end_time": 30.5,
        }
        assert isinstance(result, dict)


class TestDiarizationService:
    """Test Pyannote diarization service."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = DiarizationService()

    @pytest.mark.asyncio
    async def test_diarize_pyannote_not_available(self):
        """Test diarization when Pyannote is not installed."""
        with patch("media.audio.diarization_service._pyannote_available", False):
            service = DiarizationService()

            with pytest.raises(RuntimeError, match="Pyannote not available"):
                await service.diarize("/fake/audio.wav")

    @pytest.mark.asyncio
    async def test_diarize_success(self):
        """Test successful diarization."""
        # Create fake audio file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            audio_path = audio_file.name
            audio_file.write(b"fake audio data")

        try:
            # Mock Pyannote pipeline
            mock_annotation = MagicMock()

            # Mock itertracks to return sample segments
            mock_turn1 = MagicMock()
            mock_turn1.start = 0.0
            mock_turn1.end = 5.5

            mock_turn2 = MagicMock()
            mock_turn2.start = 5.5
            mock_turn2.end = 10.2

            mock_annotation.itertracks.return_value = [
                (mock_turn1, None, "SPEAKER_00"),
                (mock_turn2, None, "SPEAKER_01"),
            ]

            # Mock pipeline call
            mock_pipeline = MagicMock(return_value=mock_annotation)

            with patch("media.audio.diarization_service._pyannote_available", True):
                self.service._pipeline = mock_pipeline

                segments = await self.service.diarize(audio_path)

                # Verify segments
                assert len(segments) == 2

                assert segments[0].speaker_label == "SPEAKER_00"
                assert segments[0].start_time == 0.0
                assert segments[0].end_time == 5.5

                assert segments[1].speaker_label == "SPEAKER_01"
                assert segments[1].start_time == 5.5
                assert segments[1].end_time == 10.2

        finally:
            # Clean up
            import os

            if os.path.exists(audio_path):
                os.unlink(audio_path)

    @pytest.mark.asyncio
    async def test_diarize_with_speaker_constraints(self):
        """Test diarization with min/max speaker constraints."""
        # Create fake audio file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            audio_path = audio_file.name
            audio_file.write(b"fake audio data")

        try:
            # Mock Pyannote pipeline
            mock_annotation = MagicMock()
            mock_annotation.itertracks.return_value = []

            mock_pipeline = MagicMock(return_value=mock_annotation)

            with patch("media.audio.diarization_service._pyannote_available", True):
                self.service._pipeline = mock_pipeline

                segments = await self.service.diarize(audio_path, min_speakers=2, max_speakers=4)

                # Verify pipeline was called with constraints
                mock_pipeline.assert_called_once()
                call_kwargs = mock_pipeline.call_args[1]
                assert call_kwargs["min_speakers"] == 2
                assert call_kwargs["max_speakers"] == 4

        finally:
            # Clean up
            import os

            if os.path.exists(audio_path):
                os.unlink(audio_path)

    @pytest.mark.asyncio
    async def test_diarize_multiple_speakers(self):
        """Test diarization with multiple speakers and segments."""
        # Create fake audio file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            audio_path = audio_file.name
            audio_file.write(b"fake audio data")

        try:
            # Mock Pyannote pipeline with multiple speakers
            mock_annotation = MagicMock()

            # Simulate 3 speakers with overlapping segments
            segments_data = [
                (0.0, 5.0, "SPEAKER_00"),
                (5.0, 8.0, "SPEAKER_01"),
                (8.0, 12.0, "SPEAKER_00"),
                (12.0, 15.0, "SPEAKER_02"),
                (15.0, 20.0, "SPEAKER_01"),
            ]

            mock_tracks = []
            for start, end, speaker in segments_data:
                mock_turn = MagicMock()
                mock_turn.start = start
                mock_turn.end = end
                mock_tracks.append((mock_turn, None, speaker))

            mock_annotation.itertracks.return_value = mock_tracks
            mock_pipeline = MagicMock(return_value=mock_annotation)

            with patch("media.audio.diarization_service._pyannote_available", True):
                self.service._pipeline = mock_pipeline

                segments = await self.service.diarize(audio_path)

                # Verify all segments returned
                assert len(segments) == 5

                # Verify unique speakers
                unique_speakers = set(s.speaker_label for s in segments)
                assert unique_speakers == {"SPEAKER_00", "SPEAKER_01", "SPEAKER_02"}

                # Verify segment order preserved
                assert segments[0].start_time == 0.0
                assert segments[-1].end_time == 20.0

        finally:
            # Clean up
            import os

            if os.path.exists(audio_path):
                os.unlink(audio_path)

    @pytest.mark.asyncio
    async def test_diarize_error_handling(self):
        """Test diarization error handling."""
        # Create fake audio file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            audio_path = audio_file.name
            audio_file.write(b"fake audio data")

        try:
            # Mock pipeline to raise exception
            mock_pipeline = MagicMock(side_effect=Exception("Diarization processing error"))

            with patch("media.audio.diarization_service._pyannote_available", True):
                self.service._pipeline = mock_pipeline

                with pytest.raises(RuntimeError, match="Diarization failed"):
                    await self.service.diarize(audio_path)

        finally:
            # Clean up
            import os

            if os.path.exists(audio_path):
                os.unlink(audio_path)

    def test_get_diarization_service_singleton(self):
        """Test diarization service singleton behavior."""
        service1 = get_diarization_service()
        service2 = get_diarization_service()

        assert service1 is service2

    def test_is_diarization_available(self):
        """Test checking Pyannote availability."""
        # This will return the actual availability status
        available = is_diarization_available()
        assert isinstance(available, bool)


class TestDiarizationServiceIntegration:
    """Integration tests with real Pyannote (requires pyannote.audio installed)."""

    @pytest.mark.skipif(
        not is_diarization_available(),
        reason="Pyannote not installed",
    )
    @pytest.mark.asyncio
    async def test_real_diarization(self):
        """Test real diarization with Pyannote installed.

        Note: This test requires pyannote.audio and model files.
        It may download models on first run.
        """
        pytest.skip("Requires Pyannote model files and HuggingFace token")

        service = DiarizationService()

        # Would need a real audio file for full integration test
        # Skipping actual execution to avoid model download in CI
