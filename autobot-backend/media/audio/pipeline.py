# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Audio Processing Pipeline
# Issue #735: Organize media processing into dedicated pipelines
# Issue #932: Implement actual audio transcription

"""Audio processing pipeline for voice and sound content."""

import asyncio
import base64
import os
import tempfile
import threading
from dataclasses import dataclass
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from media.core.pipeline import BasePipeline
from media.core.types import MediaInput, MediaType, ProcessingResult

# Optional: transformers Whisper pipeline for transcription
try:
    from transformers import pipeline as hf_pipeline

    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    _TRANSFORMERS_AVAILABLE = False


logger = get_logger(__name__)

# Lazy singleton for the Whisper pipeline (expensive to load).
# Issue #10916: _whisper_pipeline_lock prevents two threads from both finding
# _whisper_pipeline is None and each calling hf_pipeline() concurrently.
# _WHISPER_LOADED sentinel distinguishes "not yet tried" from "tried but None".
_whisper_pipeline: Any | None = None
_whisper_pipeline_lock = threading.Lock()
_WHISPER_LOADED = False
WHISPER_MODEL = "openai/whisper-base"

#: MIME type -> temp-file suffix, for the one Whisper transcription path (#17780).
#: There were two of these maps, already drifted: this one had 8 entries and
#: ``api/voice.py`` had 6, missing ``audio/aac`` and ``audio/flac``. The same
#: mapping in two places is one mapping that disagrees with itself, so the
#: superset lives here and both callers read it.
WHISPER_MIME_SUFFIXES = {
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/webm": ".webm",
}


def suffix_for_mime(mime: str) -> str:
    """Temp-file suffix for *mime*, defaulting to ``.wav`` as both callers did."""
    return WHISPER_MIME_SUFFIXES.get(mime, ".wav")


@dataclass(frozen=True)
class WhisperTranscription:
    """What Whisper returned, before any caller-specific shaping (#17780).

    Deliberately NOT the result dict either caller returns: the two disagree on
    field names, on the confidence floor for empty text, and on whether a
    silence-hallucination filter applies. Those are real differences in what the
    two features promise, so they stay with the callers; only the inference is
    shared.
    """

    text: str
    language: str
    chunks: list


def get_whisper_pipeline() -> Any | None:
    """Lazy-load the Whisper pipeline; returns None if unavailable (thread-safe).

    Public since #17780. ``api/voice.py`` previously imported this under its
    private name from another module, which is how one loader came to serve two
    features while only one of them was pinned.
    """
    global _whisper_pipeline, _WHISPER_LOADED  # noqa: PLW0603
    if not _TRANSFORMERS_AVAILABLE:
        return None
    if not _WHISPER_LOADED:
        with _whisper_pipeline_lock:
            if not _WHISPER_LOADED:
                try:
                    # #17780: pinned and integrity-verified through
                    # `load_verified`, which is the canonical path rather than
                    # the three steps by hand. #17124 introduced it after a
                    # FAIL-OPEN bug: assigning the model before
                    # `verify_cached_model` ran left a tampered model reachable
                    # when a caller's broad `except` swallowed
                    # `ModelIntegrityError`. The `except Exception` below is
                    # exactly such a caller, so writing the steps out here --
                    # which is what my first version of this did -- would have
                    # reproduced the bug the helper exists to prevent.
                    #
                    # The registry already pins this repo (the same one
                    # `multimodal_processor/processors/voice.py` loads), so no
                    # revision is obtained here and none is invented.
                    from autobot_shared.pinned_model_registry import load_verified

                    (_whisper_pipeline,) = load_verified(
                        WHISPER_MODEL,
                        lambda revision: hf_pipeline(
                            "automatic-speech-recognition",
                            model=WHISPER_MODEL,
                            revision=revision,
                        ),
                    )
                    logger.info("Whisper pipeline loaded: %s", WHISPER_MODEL)
                except Exception as exc:
                    logger.warning("Failed to load Whisper pipeline: %s", exc)
                    _whisper_pipeline = None
                _WHISPER_LOADED = True
    return _whisper_pipeline


def transcribe_bytes(pipe: Any, audio_bytes: bytes, *, mime: str = "", language: str = "") -> WhisperTranscription:
    """Run Whisper over *audio_bytes*. BLOCKING -- call via ``asyncio.to_thread``.

    The one inference path (#17780). ``api/voice.py`` and :class:`AudioPipeline`
    each had their own copy of this: same model, same loader, same
    temp-file-plus-``to_thread`` dance, differing only in the MIME map and the
    result dict. Exceptions propagate, because the two callers disagree about
    what a failure means -- one returns empty text, the other an error result --
    and that decision belongs to them.

    *language* is a BCP-47 hint; empty means auto-detect. Passed through
    ``generate_kwargs`` only when set, preserving the voice route's behaviour
    without imposing it on the pipeline's.
    """
    with tempfile.NamedTemporaryFile(suffix=suffix_for_mime(mime), delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        generate_kwargs = {"language": language} if language else None
        output = pipe(tmp_path, return_timestamps=False, generate_kwargs=generate_kwargs)
        if not isinstance(output, dict):
            return WhisperTranscription(text="", language="unknown", chunks=[])
        return WhisperTranscription(
            text=output.get("text", "").strip(),
            language=output.get("language", "unknown"),
            chunks=output.get("chunks", []),
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


class AudioPipeline(BasePipeline):
    """Pipeline for processing audio content (voice, music, sound)."""

    PIPELINE_NAME = "audio"
    SUPPORTED_TYPES = [MediaType.AUDIO]

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
        pipe = get_whisper_pipeline()
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
        result = transcribe_bytes(pipe, raw_bytes, mime=mime)
        return self._transcription_result(result.text, result.language, result.chunks)

    def _transcription_result(self, text: str, language: str, chunks: list) -> Dict[str, Any]:
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
        """Map MIME type to file extension for temp file (one map, #17780)."""
        return suffix_for_mime(mime)

    # ------------------------------------------------------------------
    # Error/fallback helpers
    # ------------------------------------------------------------------

    def _unavailable_result(self, metadata: Dict) -> Dict[str, Any]:
        """Return structured result when Whisper/transformers not installed."""
        logger.info("Audio transcription unavailable: install transformers to enable Whisper")
        return {
            "type": "audio_transcription",
            "transcribed_text": "",
            "language": "unknown",
            "word_count": 0,
            "chunks": [],
            "processing_status": "unavailable",
            "unavailability_reason": ("transformers library not installed. " "Run: pip install transformers"),
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
