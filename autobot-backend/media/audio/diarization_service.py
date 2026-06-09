# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Pyannote Speaker Diarization Service
# Issue #9044: Speaker diarization for transcription pipeline

"""Pyannote service for speaker diarization (lazy-loaded, CPU-based)."""

import asyncio
from typing import Any, List, Optional, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Lazy imports - Pyannote is optional and heavy
_pyannote_available = False
_pipeline: Optional[Any] = None

try:
    from pyannote.audio import Pipeline

    _pyannote_available = True
except ImportError:
    logger.warning("Pyannote not available. Install with: pip install pyannote.audio")


class SpeakerSegment:
    """Speaker segment with label and timestamps."""

    def __init__(self, speaker_label: str, start_time: float, end_time: float):
        """Initialize speaker segment.

        Args:
            speaker_label: Speaker identifier (e.g., "SPEAKER_00")
            start_time: Segment start time in seconds
            end_time: Segment end time in seconds
        """
        self.speaker_label = speaker_label
        self.start_time = start_time
        self.end_time = end_time

    def to_tuple(self) -> Tuple[str, float, float]:
        """Convert to tuple format.

        Returns:
            (speaker_label, start_time, end_time)
        """
        return (self.speaker_label, self.start_time, self.end_time)

    def to_dict(self) -> dict:
        """Convert to dictionary format.

        Returns:
            Dictionary with speaker_label, start_time, end_time
        """
        return {
            "speaker_label": self.speaker_label,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


class DiarizationService:
    """Service for speaker diarization using Pyannote."""

    def __init__(self, model_name: str = "pyannote/speaker-diarization-3.1"):
        """Initialize diarization service.

        Args:
            model_name: Pyannote model identifier
        """
        self.model_name = model_name
        self._pipeline: Optional[Any] = None

    def _load_pipeline(self) -> Any:
        """Lazy-load Pyannote pipeline.

        Returns:
            Pyannote Pipeline instance

        Raises:
            RuntimeError: If Pyannote is not available
        """
        if not _pyannote_available:
            raise RuntimeError("Pyannote not available. Install with: pip install pyannote.audio")

        if self._pipeline is None:
            logger.info(f"Loading Pyannote pipeline: {self.model_name}")
            try:
                self._pipeline = Pipeline.from_pretrained(
                    self.model_name,
                    use_auth_token=None,  # Add HF token support if needed
                )
                logger.info("Pyannote pipeline loaded successfully")
            except Exception as exc:
                logger.error(f"Failed to load Pyannote pipeline: {exc}")
                raise RuntimeError(f"Failed to load Pyannote pipeline: {exc}")

        return self._pipeline

    async def diarize(
        self,
        audio_path: str,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> List[SpeakerSegment]:
        """Perform speaker diarization on audio file.

        Args:
            audio_path: Path to audio file (WAV format recommended)
            min_speakers: Minimum number of speakers (optional)
            max_speakers: Maximum number of speakers (optional)

        Returns:
            List of SpeakerSegment objects with (speaker_label, start_time, end_time)

        Raises:
            RuntimeError: If diarization fails
            FileNotFoundError: If audio file doesn't exist
        """
        pipeline = self._load_pipeline()

        logger.info(f"Running diarization on: {audio_path}")

        try:
            # Run diarization in thread to avoid blocking event loop
            diarization = await asyncio.to_thread(
                self._run_diarization, pipeline, audio_path, min_speakers, max_speakers
            )

            # Convert to speaker segments
            segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segment = SpeakerSegment(
                    speaker_label=speaker,
                    start_time=turn.start,
                    end_time=turn.end,
                )
                segments.append(segment)

            logger.info(
                f"Diarization complete: {len(segments)} segments, "
                f"{len(set(s.speaker_label for s in segments))} speakers"
            )

            return segments

        except Exception as exc:
            logger.error(f"Diarization failed: {exc}")
            raise RuntimeError(f"Diarization failed: {exc}")

    def _run_diarization(
        self,
        pipeline: Any,
        audio_path: str,
        min_speakers: Optional[int],
        max_speakers: Optional[int],
    ) -> Any:
        """Run diarization (blocking, called via asyncio.to_thread).

        Args:
            pipeline: Pyannote Pipeline instance
            audio_path: Path to audio file
            min_speakers: Minimum speakers
            max_speakers: Maximum speakers

        Returns:
            Pyannote Annotation object
        """
        kwargs = {}
        if min_speakers is not None:
            kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            kwargs["max_speakers"] = max_speakers

        return pipeline(audio_path, **kwargs)


# Singleton instance
_diarization_service: Optional[DiarizationService] = None


def get_diarization_service() -> DiarizationService:
    """Get or create diarization service singleton.

    Returns:
        DiarizationService instance
    """
    global _diarization_service
    if _diarization_service is None:
        _diarization_service = DiarizationService()
    return _diarization_service


def is_diarization_available() -> bool:
    """Check if Pyannote is available.

    Returns:
        True if Pyannote is installed and available
    """
    return _pyannote_available
