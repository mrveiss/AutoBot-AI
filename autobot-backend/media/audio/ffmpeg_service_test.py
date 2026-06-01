# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# FFmpeg Service Tests
# Issue #9044: Audio extraction and normalization tests

"""Tests for FFmpeg audio processing service."""

import asyncio
import os
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from media.audio.ffmpeg_service import FFmpegService, get_ffmpeg_service


class TestFFmpegService:
    """Test FFmpeg audio extraction and normalization."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = FFmpegService()

    @pytest.mark.asyncio
    async def test_extract_audio_success(self):
        """Test successful audio extraction."""
        # Create a dummy input file
        with tempfile.NamedTemporaryFile(
            suffix=".mp3", delete=False
        ) as input_file:
            input_path = input_file.name
            input_file.write(b"fake audio data")

        try:
            # Mock subprocess
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))

            with patch(
                "asyncio.create_subprocess_exec", return_value=mock_process
            ):
                output_path = await self.service.extract_audio(
                    input_path, sample_rate=16000, channels=1
                )

                # Verify output path exists
                assert output_path is not None
                assert output_path.endswith(".wav")

                # Verify subprocess was called with correct arguments
                mock_process.communicate.assert_called_once()

        finally:
            # Clean up
            if os.path.exists(input_path):
                os.unlink(input_path)
            if "output_path" in locals() and os.path.exists(output_path):
                os.unlink(output_path)

    @pytest.mark.asyncio
    async def test_extract_audio_file_not_found(self):
        """Test extraction with non-existent input file."""
        with pytest.raises(FileNotFoundError):
            await self.service.extract_audio("/nonexistent/file.mp3")

    @pytest.mark.asyncio
    async def test_extract_audio_ffmpeg_error(self):
        """Test extraction when FFmpeg command fails."""
        # Create a dummy input file
        with tempfile.NamedTemporaryFile(
            suffix=".mp3", delete=False
        ) as input_file:
            input_path = input_file.name
            input_file.write(b"fake audio data")

        try:
            # Mock subprocess failure
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(
                return_value=(b"", b"FFmpeg error: invalid format")
            )

            with patch(
                "asyncio.create_subprocess_exec", return_value=mock_process
            ):
                with pytest.raises(RuntimeError, match="FFmpeg extraction failed"):
                    await self.service.extract_audio(input_path)

        finally:
            # Clean up
            if os.path.exists(input_path):
                os.unlink(input_path)

    @pytest.mark.asyncio
    async def test_extract_audio_custom_parameters(self):
        """Test extraction with custom sample rate and channels."""
        # Create a dummy input file
        with tempfile.NamedTemporaryFile(
            suffix=".mp3", delete=False
        ) as input_file:
            input_path = input_file.name
            input_file.write(b"fake audio data")

        try:
            # Mock subprocess
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))

            with patch(
                "asyncio.create_subprocess_exec", return_value=mock_process
            ) as mock_exec:
                await self.service.extract_audio(
                    input_path, sample_rate=48000, channels=2
                )

                # Verify FFmpeg was called with correct parameters
                call_args = mock_exec.call_args[0]
                assert "48000" in call_args
                assert "2" in call_args

        finally:
            # Clean up
            if os.path.exists(input_path):
                os.unlink(input_path)

    @pytest.mark.asyncio
    async def test_get_audio_duration_success(self):
        """Test getting audio duration with FFprobe."""
        # Create a dummy audio file
        with tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False
        ) as audio_file:
            audio_path = audio_file.name
            audio_file.write(b"fake audio data")

        try:
            # Mock subprocess
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"42.5\n", b""))

            with patch(
                "asyncio.create_subprocess_exec", return_value=mock_process
            ):
                duration = await self.service.get_audio_duration(audio_path)

                assert duration == 42.5

        finally:
            # Clean up
            if os.path.exists(audio_path):
                os.unlink(audio_path)

    @pytest.mark.asyncio
    async def test_get_audio_duration_error(self):
        """Test duration retrieval when FFprobe fails."""
        # Create a dummy audio file
        with tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False
        ) as audio_file:
            audio_path = audio_file.name
            audio_file.write(b"fake audio data")

        try:
            # Mock subprocess failure
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(
                return_value=(b"", b"FFprobe error")
            )

            with patch(
                "asyncio.create_subprocess_exec", return_value=mock_process
            ):
                with pytest.raises(RuntimeError, match="FFprobe failed"):
                    await self.service.get_audio_duration(audio_path)

        finally:
            # Clean up
            if os.path.exists(audio_path):
                os.unlink(audio_path)

    def test_get_ffmpeg_service_singleton(self):
        """Test FFmpeg service singleton behavior."""
        service1 = get_ffmpeg_service()
        service2 = get_ffmpeg_service()

        assert service1 is service2


class TestFFmpegServiceIntegration:
    """Integration tests with real FFmpeg (requires FFmpeg installed)."""

    @pytest.mark.skipif(
        shutil.which("ffmpeg") is None,
        reason="FFmpeg not installed",
    )
    @pytest.mark.asyncio
    async def test_real_audio_extraction(self):
        """Test real audio extraction with FFmpeg installed."""
        service = FFmpegService()

        # Create a minimal WAV file (1 second of silence)
        with tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False
        ) as input_file:
            input_path = input_file.name
            # Write a minimal valid WAV header + data
            wav_data = self._create_minimal_wav()
            input_file.write(wav_data)

        try:
            # Extract and normalize
            output_path = await service.extract_audio(
                input_path, sample_rate=16000, channels=1
            )

            # Verify output exists
            assert os.path.exists(output_path)
            assert os.path.getsize(output_path) > 0

            # Clean up output
            os.unlink(output_path)

        finally:
            # Clean up input
            if os.path.exists(input_path):
                os.unlink(input_path)

    def _create_minimal_wav(self) -> bytes:
        """Create a minimal valid WAV file (44 bytes header + 1 byte data)."""
        return (
            b"RIFF"
            + (36).to_bytes(4, "little")  # Chunk size
            + b"WAVE"
            + b"fmt "
            + (16).to_bytes(4, "little")  # Subchunk1 size
            + (1).to_bytes(2, "little")  # Audio format (PCM)
            + (1).to_bytes(2, "little")  # Num channels
            + (16000).to_bytes(4, "little")  # Sample rate
            + (32000).to_bytes(4, "little")  # Byte rate
            + (2).to_bytes(2, "little")  # Block align
            + (16).to_bytes(2, "little")  # Bits per sample
            + b"data"
            + (0).to_bytes(4, "little")  # Subchunk2 size
        )
