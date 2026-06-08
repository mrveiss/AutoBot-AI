# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# FFmpeg Audio Processing Service
# Issue #9044: Audio extraction and normalization for transcription pipeline
# Issue #9214: Security hardening against path injection

"""FFmpeg service for audio extraction and normalization to WAV format."""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Allowed audio extensions (must match upload_security.py)
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".mp4", ".m4a", ".ogg", ".flac", ".webm"}

# Extension to FFmpeg format mapping (for -f flag)
EXTENSION_TO_FORMAT = {
    ".wav": "wav",
    ".mp3": "mp3",
    ".mp4": "mp4",
    ".m4a": "m4a",
    ".ogg": "ogg",
    ".flac": "flac",
    ".webm": "webm",
}


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

        Security hardening (Issue #9214):
        - Extension whitelist validation
        - Protocol whitelist (blocks HLS/HTTP demuxers)
        - Demuxer pinning with -f flag
        - Path validation (must be absolute)

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
            ValueError: If file extension is not allowed
        """
        # Security: Validate extension
        input_ext = Path(input_path).suffix.lower()
        if input_ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"File extension '{input_ext}' not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

        # Security: Reject relative paths
        if not os.path.isabs(input_path):
            raise ValueError(f"Only absolute paths allowed: {input_path}")

        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Security: Reject symlinks
        if os.path.islink(input_path):
            raise ValueError(f"Symlinks not allowed: {input_path}")

        # Create output path if not provided
        if output_path is None:
            temp_fd, output_path = tempfile.mkstemp(suffix=".wav", prefix="audio_")
            os.close(temp_fd)

        # Get format for demuxer pinning
        input_format = EXTENSION_TO_FORMAT.get(input_ext)

        # Build FFmpeg command with security hardening
        cmd = [
            self.ffmpeg_path,
            # Security: Protocol whitelist (blocks HLS/HTTP/etc.)
            "-protocol_whitelist",
            "file",
            # Security: Extension whitelist (using allowed_extensions)
            "-allowed_extensions",
            ",".join(ext.lstrip(".") for ext in ALLOWED_EXTENSIONS),
        ]

        # Security: Pin demuxer with -f flag if known
        if input_format:
            cmd.extend(["-f", input_format])

        cmd.extend(
            [
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
        )

        logger.info("Extracting audio: %s → %s", input_path, output_path)
        logger.debug("FFmpeg command: %s", " ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                logger.error("FFmpeg extraction failed: %s", error_msg)
                raise RuntimeError(f"FFmpeg extraction failed: {error_msg}")

            logger.info("Audio extracted successfully to %s", output_path)
            return output_path

        except FileNotFoundError:
            raise RuntimeError(f"FFmpeg not found at {self.ffmpeg_path}. Please install FFmpeg: apt-get install ffmpeg")
        except Exception as exc:
            logger.error("Audio extraction error: %s", exc)
            # Clean up output file on error
            if os.path.exists(output_path):
                try:
                    os.unlink(output_path)
                except OSError:
                    pass
            raise

    async def get_audio_duration(self, file_path: str) -> float:
        """Get audio duration in seconds using FFprobe.

        Security: Validates extension and rejects symlinks.

        Args:
            file_path: Path to audio file

        Returns:
            Duration in seconds

        Raises:
            RuntimeError: If FFprobe fails
            ValueError: If file extension is not allowed or path is symlink
        """
        # Security: Validate extension
        file_ext = Path(file_path).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"File extension '{file_ext}' not allowed")

        # Security: Reject symlinks
        if os.path.islink(file_path):
            raise ValueError(f"Symlinks not allowed: {file_path}")

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
            logger.error("Failed to get audio duration: %s", exc)
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
