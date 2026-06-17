# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Transcriber Orchestrator
# Issue #9044, #9214, #10128

"""Orchestration service for the transcription pipeline."""

import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from media.audio.diarization_service import SpeakerSegment, get_diarization_service, is_diarization_available
from media.audio.ffmpeg_service import get_ffmpeg_service
from transcriber.database import Database, get_transcriber_db
from transcriber.models import RecordingStatus
from voice_processing.language_detection import detect_language
from voice_processing.providers import TranscriptSegment, get_speech_provider_registry

logger = get_logger(__name__)

_SINGLE_SPEAKER_LABEL = "SPEAKER_00"


class TranscriberOrchestrator:
    """Orchestrates the transcription pipeline with speaker diarization."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db
        self.ffmpeg_service = get_ffmpeg_service()
        self.diarization_service = get_diarization_service()
        self.provider_registry = get_speech_provider_registry()

    async def process_recording(self, recording_id: int) -> dict:
        """Process a recording through the full pipeline.

        Pipeline stages:
        1. Validate + guard status
        2. Extract and normalize audio (FFmpeg)
        3. Detect language
        4. Speaker diarization (Pyannote, or single-speaker fallback)
        5. Transcribe audio
        6. Merge transcription segments with speakers by time-overlap
        7. Persist speakers + segments to database
        """
        if self.db is None:
            self.db = await get_transcriber_db()

        recording = await self.db.get_recording(recording_id)
        if recording is None:
            raise ValueError(f"Recording {recording_id} not found")

        if recording["status"] != RecordingStatus.PENDING.value:
            raise ValueError(f"Recording {recording_id} is not pending (current: {recording['status']})")

        _validate_file_path(recording["filepath"])

        await self.db.update_recording_status(recording_id, RecordingStatus.PROCESSING.value)

        start_ts = time.monotonic()
        tmp_wav_path: Optional[str] = None
        try:
            tmp_wav_path = await self._extract_audio(recording_id, recording["filepath"])
            duration = await self.ffmpeg_service.get_audio_duration(tmp_wav_path)
            await self.db.update_recording_duration(recording_id, duration)
            logger.info("Recording %d: audio duration=%.2fs", recording_id, duration)

            language = await detect_language(audio_path=tmp_wav_path, filename_hint=recording["filename"])
            logger.info("Recording %d: detected language=%s", recording_id, language)

            provider = self.provider_registry.get_provider(language)
            transcript_segments = await self._transcribe_with_provider(tmp_wav_path, language, provider)

            if _provider_diarizes(provider, transcript_segments):
                logger.info(
                    "Recording %d: provider %r supplies diarization — skipping Pyannote",
                    recording_id,
                    getattr(provider, "provider_name", "?"),
                )
                speaker_ids = await self._persist_speakers_from_segments(recording_id, transcript_segments, language)
                await self._persist_segments_diarized(recording_id, transcript_segments, speaker_ids)
            else:
                speaker_segments = await self._diarize(tmp_wav_path)
                speaker_ids = await self._persist_speakers(recording_id, speaker_segments, language)
                await self._persist_segments(recording_id, transcript_segments, speaker_segments, speaker_ids)

            speaker_count = len(speaker_ids)
            process_seconds = time.monotonic() - start_ts
            engine_name = provider.provider_name if provider else None
            await self.db.update_recording_status(
                recording_id,
                RecordingStatus.COMPLETE.value,
                language_detected=language,
                speaker_count=speaker_count,
                process_seconds=process_seconds,
                engine_used=engine_name,
            )
            logger.info(
                "Recording %d complete: speakers=%d segments=%d engine=%s",
                recording_id,
                speaker_count,
                len(transcript_segments),
                engine_name,
            )
            return {
                "recording_id": recording_id,
                "status": RecordingStatus.COMPLETE.value,
                "segments_count": len(transcript_segments),
                "language": language,
                "duration": duration,
            }

        except Exception as exc:
            process_seconds = time.monotonic() - start_ts
            failure_stage = type(exc).__name__
            logger.error("Recording %d failed at %s", recording_id, failure_stage)
            await self.db.update_recording_status(
                recording_id,
                RecordingStatus.ERROR.value,
                process_seconds=process_seconds,
                failure_stage=failure_stage,
                failure_reason="Processing failed — see backend logs",
            )
            raise
        finally:
            if tmp_wav_path:
                Path(tmp_wav_path).unlink(missing_ok=True)

    # ── private helpers ───────────────────────────────────────────────────────

    async def _extract_audio(self, recording_id: int, filepath: str) -> str:
        """Extract audio to a temporary WAV file; return the tmp path."""
        logger.info("Recording %d: extracting audio from %s", recording_id, filepath)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        await self.ffmpeg_service.extract_audio(input_path=filepath, output_path=tmp_path)
        return tmp_path

    async def _diarize(self, wav_path: str) -> List[SpeakerSegment]:
        """Diarize audio; return single-speaker fallback if Pyannote unavailable."""
        if not is_diarization_available():
            logger.info("Pyannote unavailable — using single-speaker fallback")
            return []
        try:
            segments = await self.diarization_service.diarize(wav_path)
            logger.info("Diarization: %d segments", len(segments))
            return segments
        except Exception as exc:
            logger.warning("Diarization failed (%s) — using single-speaker fallback", exc)
            return []

    async def _transcribe_with_provider(
        self, wav_path: str, language: str, provider: Optional[object]
    ) -> List[TranscriptSegment]:
        """Transcribe using the given provider; raise when provider is None."""
        if provider is None:
            raise ValueError(f"No speech provider available for language: {language}")
        logger.info("Transcribing with %s (lang=%s)", getattr(provider, "provider_name", "?"), language)
        result = await provider.transcribe(wav_path, language)  # type: ignore[union-attr]
        if result is None:
            raise ValueError("Transcription returned None")
        return result

    async def _persist_speakers_from_segments(
        self,
        recording_id: int,
        transcript_segments: List[TranscriptSegment],
        language: str,
    ) -> Dict[str, int]:
        """Create speaker rows from provider-supplied speaker labels on segments.

        Used by the diarizing-provider F4 branch (Issue #10147).
        """
        labels = sorted({s.speaker for s in transcript_segments if s.speaker} or [_SINGLE_SPEAKER_LABEL])
        label_to_id: Dict[str, int] = {}
        for label in labels:
            sid = await self.db.create_speaker(recording_id, label=label, display_name=label, language=language)
            label_to_id[label] = sid
        return label_to_id

    async def _persist_segments_diarized(
        self,
        recording_id: int,
        transcript_segments: List[TranscriptSegment],
        speaker_ids: Dict[str, int],
    ) -> None:
        """Persist segments where speaker is already set by the provider (F4 path)."""
        for seg in transcript_segments:
            label = seg.speaker or _SINGLE_SPEAKER_LABEL
            speaker_id = speaker_ids.get(label, speaker_ids.get(_SINGLE_SPEAKER_LABEL))
            await self.db.create_segment(
                recording_id,
                speaker_id=speaker_id,
                start_time=seg.start_time,
                end_time=seg.end_time,
                text=seg.text,
            )

    async def _persist_speakers(
        self,
        recording_id: int,
        diar_segments: List[SpeakerSegment],
        language: str,
    ) -> Dict[str, int]:
        """Create speaker rows; return {label: speaker_id}."""
        if diar_segments:
            labels = sorted({s.speaker_label for s in diar_segments})
        else:
            labels = [_SINGLE_SPEAKER_LABEL]

        label_to_id: Dict[str, int] = {}
        for label in labels:
            sid = await self.db.create_speaker(recording_id, label=label, display_name=label, language=language)
            label_to_id[label] = sid
        return label_to_id

    async def _persist_segments(
        self,
        recording_id: int,
        transcript_segments: List[TranscriptSegment],
        diar_segments: List[SpeakerSegment],
        speaker_ids: Dict[str, int],
    ) -> None:
        """Write transcript segments with speaker assignment to the database."""
        for seg in transcript_segments:
            label = _assign_speaker(seg, diar_segments)
            speaker_id = speaker_ids.get(label, speaker_ids.get(_SINGLE_SPEAKER_LABEL))
            await self.db.create_segment(
                recording_id,
                speaker_id=speaker_id,
                start_time=seg.start_time,
                end_time=seg.end_time,
                text=seg.text,
            )


def _provider_diarizes(provider: Optional[object], segments: List[TranscriptSegment]) -> bool:
    """Return True if the provider declares it diarizes AND produced speaker-labeled segments.

    Checks the provider's `diarizes` attribute (set to True on CloudSpeechProvider)
    and confirms at least one segment carries a .speaker label.
    """
    if provider is None:
        return False
    if not getattr(provider, "diarizes", False):
        return False
    return any(s.speaker for s in segments)


def _validate_file_path(filepath: str) -> None:
    """Raise ValueError for insecure or missing paths (Issue #9214)."""
    from transcriber.upload_security import get_upload_base_dir

    if not Path(filepath).is_absolute():
        raise ValueError(f"Path must be absolute: {filepath}")
    upload_base = get_upload_base_dir()
    try:
        Path(filepath).resolve().relative_to(upload_base)
    except ValueError:
        raise ValueError(f"Path traversal blocked: {filepath} not in {upload_base}")
    if not Path(filepath).exists():
        raise ValueError(f"File not found: {filepath}")
    if Path(filepath).is_symlink():
        raise ValueError(f"Symlinks not allowed: {filepath}")


def _assign_speaker(seg: TranscriptSegment, diar_segments: List[SpeakerSegment]) -> str:
    """Return the speaker label with maximum time-overlap with the transcript segment.

    Falls back to SPEAKER_00 when diarization produced no segments.
    """
    if not diar_segments:
        return _SINGLE_SPEAKER_LABEL
    best_label = _SINGLE_SPEAKER_LABEL
    best_overlap = 0.0
    for ds in diar_segments:
        overlap = max(0.0, min(seg.end_time, ds.end_time) - max(seg.start_time, ds.start_time))
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = ds.speaker_label
    return best_label


# ── Singleton ──────────────────────────────────────────────────────────────────

_orchestrator: Optional[TranscriberOrchestrator] = None


def get_transcriber_orchestrator() -> TranscriberOrchestrator:
    """Return (or create) the module-level orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = TranscriberOrchestrator()
    return _orchestrator
