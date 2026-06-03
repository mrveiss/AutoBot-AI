# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# FFmpeg Audio Processing Service
# Issue #9044: Audio extraction and normalization for transcription pipeline

"""FFmpeg service for audio extraction and normalization to WAV format."""

import asyncio
import os
import tempfile
from typing import Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class FFmpegService:
    """Service for audio extraction and normalization using FFmpeg."""

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        """Initialize FFmpeg service.

        Args:
            ffmpeg_path: Path to ffmpeg binary (default: "ffmpeg" from PATH)
        """
        self.ffmpeg_path = ffmpeg_path

    async def extract_audio(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> str:
        """Extract and normalize audio to WAV format.

        Args:
            input_path: Path to input audio/video file
            output_path: Optional output path (creates temp file if not provided)
            sample_rate: Target sample rate in Hz (default: 16000)
            channels: Number of audio channels (default: 1 for mono)

        Returns:
            Path to normalized WAV file

        Raises:
            RuntimeError: If FFmpeg extraction fails
            FileNotFoundError: If input file doesn't exist
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Create output path if not provided
        if output_path is None:
            temp_fd, output_path = tempfile.mkstemp(suffix=".wav", prefix="audio_")
            os.close(temp_fd)

        # Build FFmpeg command for extraction and normalization
        cmd = [
            self.ffmpeg_path,
            "-i",
            input_path,
            "-vn",  # No video
            "-acodec",
            "pcm_s16le",  # PCM 16-bit little-endian
            "-ar",
            str(sample_rate),  # Sample rate
            "-ac",
            str(channels),  # Mono/stereo
            "-y",  # Overwrite output
            output_path,
        ]

        logger.info(f"Extracting audio: {input_path} → {output_path}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                logger.error(f"FFmpeg extraction failed: {error_msg}")
                raise RuntimeError(f"FFmpeg extraction failed: {error_msg}")

            logger.info(f"Audio extracted successfully to {output_path}")
            return output_path

        except FileNotFoundError:
            raise RuntimeError(
                f"FFmpeg not found at {self.ffmpeg_path}. " "Please install FFmpeg: apt-get install ffmpeg"
            )
        except Exception as exc:
            logger.error(f"Audio extraction error: {exc}")
            # Clean up output file on error
            if os.path.exists(output_path):
                try:
                    os.unlink(output_path)
                except OSError:
                    pass
            raise

    async def get_audio_duration(self, file_path: str) -> float:
        """Get audio duration in seconds using FFprobe.

        Args:
            file_path: Path to audio file

        Returns:
            Duration in seconds

        Raises:
            RuntimeError: If FFprobe fails
        """
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                raise RuntimeError(f"FFprobe failed: {error_msg}")

            duration_str = stdout.decode("utf-8").strip()
            return float(duration_str)

        except (ValueError, FileNotFoundError) as exc:
            logger.error(f"Failed to get audio duration: {exc}")
            raise RuntimeError(f"Failed to get audio duration: {exc}")


# Singleton instance
_ffmpeg_service: Optional[FFmpegService] = None


def get_ffmpeg_service() -> FFmpegService:
    """Get or create FFmpeg service singleton.

    Returns:
        FFmpegService instance
    """
    global _ffmpeg_service
    if _ffmpeg_service is None:
        _ffmpeg_service = FFmpegService()
    return _ffmpeg_service
