# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Audio Processing Pipeline
# Issue #735: Organize media processing into dedicated pipelines
# Issue #932: Implement actual audio transcription

"""Audio processing pipeline for voice and sound content."""

import asyncio
import base64
import logging
import os
import tempfile
from typing import Any, Dict, Optional

from media.core.pipeline import BasePipeline
from media.core.types import MediaInput, MediaType, ProcessingResult

# Optional: transformers Whisper pipeline for transcription
try:
    from transformers import pipeline as hf_pipeline

    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    _TRANSFORMERS_AVAILABLE = False


logger = logging.getLogger(__name__)

# Lazy singleton for the Whisper pipeline (expensive to load)
_whisper_pipeline: Optional[Any] = None
_WHISPER_MODEL = "openai/whisper-base"


def _get_whisper_pipeline() -> Optional[Any]:
    """Lazy-load Whisper pipeline; returns None if unavailable."""
    global _whisper_pipeline
    if not _TRANSFORMERS_AVAILABLE:
        return None
    if _whisper_pipeline is None:
        try:
            _whisper_pipeline = hf_pipeline(
                "automatic-speech-recognition",
                model=_WHISPER_MODEL,
            )
            logger.info("Whisper pipeline loaded: %s", _WHISPER_MODEL)
        except Exception as exc:
            logger.warning("Failed to load Whisper pipeline: %s", exc)
    return _whisper_pipeline


class AudioPipeline(BasePipeline):
    """Pipeline for processing audio content (voice, music, sound)."""

    def __init__(self):
        """Initialize audio processing pipeline."""
        super().__init__(
            pipeline_name="audio",
            supported_types=[MediaType.AUDIO],
        )

    async def _process_impl(self, media_input: MediaInput) -> ProcessingResult:
        """Process audio content."""
        result_data = await self._process_audio(media_input)
        confidence = self._calculate_confidence(result_data)

        return ProcessingResult(
            result_id=f"audio_{media_input.media_id}",
            media_id=media_input.media_id,
            media_type=media_input.media_type,
            intent=media_input.intent,
            success=True,
            confidence=confidence,
            result_data=result_data,
            processing_time=0.0,  # Set by BasePipeline
        )

    async def _process_audio(self, media_input: MediaInput) -> Dict[str, Any]:
        """Transcribe audio using Whisper if available, or return metadata."""
        pipe = _get_whisper_pipeline()
        if not pipe:
            return self._unavailable_result(media_input.metadata)

        raw_bytes = self._decode_input(media_input.data)
        mime = (media_input.mime_type or "").lower()

        # Run Whisper in a thread to avoid blocking the event loop
        try:
            result = await asyncio.to_thread(self._run_whisper, pipe, raw_bytes, mime)
            return result
        except Exception as exc:
            logger.warning("Audio transcription failed: %s", exc)
            return self._error_result(str(exc), media_input.metadata)

    def _run_whisper(self, pipe: Any, raw_bytes: bytes, mime: str) -> Dict[str, Any]:
        """Execute Whisper transcription (blocking, run via asyncio.to_thread)."""
        # Write to a temp file so Whisper can read it
        suffix = self._suffix_from_mime(mime)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        try:
            output = pipe(tmp_path, return_timestamps=False)
            text = output.get("text", "").strip() if isinstance(output, dict) else ""
            chunks = output.get("chunks", []) if isinstance(output, dict) else []
            language = (
                output.get("language", "unknown")
                if isinstance(output, dict)
                else "unknown"
            )
            return self._transcription_result(text, language, chunks)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _transcription_result(
        self, text: str, language: str, chunks: list
    ) -> Dict[str, Any]:
        """Build the transcription result dict."""
        confidence = 0.9 if text else 0.5
        return {
            "type": "audio_transcription",
            "transcribed_text": text,
            "language": language,
            "word_count": len(text.split()) if text else 0,
            "chunks": chunks,
            "processing_method": "whisper",
            "confidence": confidence,
        }

    # ------------------------------------------------------------------
    # Input decoding helpers
    # ------------------------------------------------------------------

    def _decode_input(self, data: Any) -> bytes:
        """Normalize input data to raw bytes."""
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            # Base64 first, then file path
            try:
                return base64.b64decode(data)
            except Exception:
                with open(data, "rb") as fh:
                    return fh.read()
        raise ValueError(f"Unsupported audio data type: {type(data)}")

    def _suffix_from_mime(self, mime: str) -> str:
        """Map MIME type to file extension for temp file."""
        mapping = {
            "audio/mpeg": ".mp3",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/ogg": ".ogg",
            "audio/mp4": ".m4a",
            "audio/aac": ".aac",
            "audio/flac": ".flac",
            "audio/webm": ".webm",
        }
        return mapping.get(mime, ".wav")

    # ------------------------------------------------------------------
    # Error/fallback helpers
    # ------------------------------------------------------------------

    def _unavailable_result(self, metadata: Dict) -> Dict[str, Any]:
        """Return structured result when Whisper/transformers not installed."""
        logger.info(
            "Audio transcription unavailable: install transformers to enable Whisper"
        )
        return {
            "type": "audio_transcription",
            "transcribed_text": "",
            "language": "unknown",
            "word_count": 0,
            "chunks": [],
            "processing_status": "unavailable",
            "unavailability_reason": (
                "transformers library not installed. " "Run: pip install transformers"
            ),
            "confidence": 0.0,
            "metadata": metadata,
        }

    def _error_result(self, error: str, metadata: Dict) -> Dict[str, Any]:
        """Return structured result on transcription error."""
        return {
            "type": "audio_transcription",
            "transcribed_text": "",
            "language": "unknown",
            "word_count": 0,
            "chunks": [],
            "processing_status": "error",
            "error": error,
            "confidence": 0.0,
            "metadata": metadata,
        }

    def _calculate_confidence(self, result_data: Dict[str, Any]) -> float:
        """Calculate confidence score from result data."""
        return result_data.get("confidence", 0.5)
