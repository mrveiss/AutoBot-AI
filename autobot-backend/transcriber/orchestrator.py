# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Transcriber Orchestrator
# Issue #9044

"""Orchestration service for transcription pipeline."""

import tempfile
from pathlib import Path
from typing import List, Optional

from autobot_shared.logging_manager import get_logger
from media.audio.diarization_service import get_diarization_service
from media.audio.ffmpeg_service import get_ffmpeg_service
from transcriber.database import TranscriberDatabase, get_transcriber_db
from transcriber.models import RecordingStatus, TranscriptionSegment
from voice_processing.language_detection import detect_language
from voice_processing.providers import get_provider_registry

logger = get_logger(__name__)


class TranscriberOrchestrator:
    """Orchestrates the transcription pipeline with speaker diarization."""

    def __init__(self, db: Optional[TranscriberDatabase] = None):
        """Initialize orchestrator.

        Args:
            db: Optional TranscriberDatabase instance (for testing)
        """
        self.db = db
        self.ffmpeg_service = get_ffmpeg_service()
        self.diarization_service = get_diarization_service()
        self.provider_registry = get_provider_registry()

    async def process_recording(self, recording_id: int) -> dict:
        """Process a recording through the full pipeline.

        Pipeline stages:
        1. Extract and normalize audio with FFmpeg
        2. Detect language
        3. Generate speaker segments with Pyannote diarization
        4. Transcribe audio with language-appropriate speech provider
        5. Merge transcription text with speaker timestamps
        6. Persist segments to database

        Args:
            recording_id: Recording ID to process

        Returns:
            Dictionary with processing results

        Raises:
            Exception: If processing fails at any stage
        """
        # Get database if not injected
        if self.db is None:
            self.db = await get_transcriber_db()

        # Get recording
        recording = await self.db.get_recording(recording_id)
        if recording is None:
            raise ValueError(f"Recording {recording_id} not found")

        if recording.status != RecordingStatus.PENDING:
            raise ValueError(f"Recording {recording_id} is not in pending status (current: {recording.status})")

        # Update status to processing
        await self.db.update_recording_status(recording_id, RecordingStatus.PROCESSING)

        try:
            # Stage 1: Extract and normalize audio
            logger.info(
                "Stage 1/5: Extracting and normalizing audio for recording %d",
                recording_id,
            )
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                tmp_wav_path = tmp_wav.name

            await self.ffmpeg_service.extract_audio(input_path=recording.file_path, output_path=tmp_wav_path)

            # Get audio duration
            duration = await self.ffmpeg_service.get_audio_duration(tmp_wav_path)
            logger.info("Audio duration: %.2f seconds", duration)

            # Stage 2: Detect language
            logger.info("Stage 2/5: Detecting language")
            language = await detect_language(audio_path=tmp_wav_path, filename_hint=recording.filename)
            logger.info("Detected language: %s", language)

            await self.db.update_recording_status(
                recording_id, RecordingStatus.PROCESSING, duration=duration, language=language
            )

            # Stage 3: Speaker diarization
            logger.info("Stage 3/5: Performing speaker diarization")
            speaker_segments = await self.diarization_service.diarize(tmp_wav_path)
            logger.info("Found %d speaker segments", len(speaker_segments))

            # Stage 4: Speech recognition
            logger.info("Stage 4/5: Transcribing audio (language: %s)", language)
            provider = self.provider_registry.get_provider(language)
            if provider is None:
                raise ValueError(f"No speech provider available for language: {language}")

            logger.info("Using provider: %s", provider.__class__.__name__)
            transcription_result = await provider.transcribe(tmp_wav_path, language)

            if transcription_result is None:
                raise ValueError("Transcription failed - no result returned")

            # Stage 5: Merge diarization with transcription
            logger.info("Stage 5/5: Merging diarization with transcription")
            merged_segments = self._merge_segments(
                speaker_segments=speaker_segments,
                transcription_text=transcription_result.get("text", ""),
                confidence=transcription_result.get("confidence", 0.95),
            )

            logger.info("Merged into %d final segments", len(merged_segments))

            # Persist segments to database
            created_segments = await self.db.create_segments(segments=merged_segments, recording_id=recording_id)

            # Update recording status to completed
            await self.db.update_recording_status(recording_id, RecordingStatus.COMPLETED)

            # Clean up temp file
            Path(tmp_wav_path).unlink(missing_ok=True)

            logger.info(
                "Recording %d processed successfully: %d segments",
                recording_id,
                len(created_segments),
            )

            return {
                "recording_id": recording_id,
                "status": RecordingStatus.COMPLETED.value,
                "segments_count": len(created_segments),
                "language": language,
                "duration": duration,
            }

        except Exception as exc:
            logger.error("Processing failed for recording %d: %s", recording_id, exc)
            await self.db.update_recording_status(recording_id, RecordingStatus.FAILED)

            # Clean up temp file if it exists
            try:
                Path(tmp_wav_path).unlink(missing_ok=True)
            except Exception:
                pass

            raise

    def _merge_segments(
        self,
        speaker_segments: List,
        transcription_text: str,
        confidence: float,
    ) -> List[dict]:
        """Merge speaker segments with transcription text.

        Algorithm:
        1. Split transcription text by words
        2. Distribute words proportionally across speaker segments based on duration
        3. Assign each segment its portion of the text

        Args:
            speaker_segments: List of SpeakerSegment objects from diarization
            transcription_text: Full transcription text
            confidence: Overall confidence score

        Returns:
            List of merged segment dictionaries with speaker_label, start_time, end_time, text, confidence
        """
        if not speaker_segments:
            logger.warning("No speaker segments - returning empty list")
            return []

        if not transcription_text.strip():
            logger.warning("Empty transcription text - returning segments with empty text")
            return [
                {
                    "speaker_label": seg.speaker,
                    "start_time": seg.start,
                    "end_time": seg.end,
                    "text": "",
                    "confidence": confidence,
                }
                for seg in speaker_segments
            ]

        # Split text into words
        words = transcription_text.split()
        total_duration = sum(seg.end - seg.start for seg in speaker_segments)

        if total_duration == 0:
            logger.warning("Total duration is 0 - equal word distribution")
            words_per_segment = len(words) // len(speaker_segments)
            remainder = len(words) % len(speaker_segments)
        else:
            words_per_segment = None
            remainder = 0

        merged = []
        word_index = 0

        for i, seg in enumerate(speaker_segments):
            # Calculate how many words for this segment based on duration proportion
            if words_per_segment is None:
                segment_duration = seg.end - seg.start
                proportion = segment_duration / total_duration
                num_words = round(proportion * len(words))
            else:
                num_words = words_per_segment + (1 if i < remainder else 0)

            # Ensure we don't exceed available words
            num_words = min(num_words, len(words) - word_index)

            # Extract words for this segment
            segment_words = words[word_index : word_index + num_words]
            segment_text = " ".join(segment_words)

            # Create merged segment
            merged.append(
                {
                    "speaker_label": seg.speaker,
                    "start_time": seg.start,
                    "end_time": seg.end,
                    "text": segment_text,
                    "confidence": confidence,
                }
            )

            word_index += num_words

        # If any words remain, append to last segment
        if word_index < len(words):
            remaining_words = " ".join(words[word_index:])
            if merged:
                merged[-1]["text"] += " " + remaining_words
            else:
                # Fallback: create a single segment with all text
                merged.append(
                    {
                        "speaker_label": "SPEAKER_00",
                        "start_time": 0.0,
                        "end_time": total_duration,
                        "text": transcription_text,
                        "confidence": confidence,
                    }
                )

        return merged


# Singleton instance
_orchestrator: Optional[TranscriberOrchestrator] = None


def get_transcriber_orchestrator() -> TranscriberOrchestrator:
    """Get or create transcriber orchestrator singleton.

    Returns:
        TranscriberOrchestrator instance
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = TranscriberOrchestrator()
    return _orchestrator
