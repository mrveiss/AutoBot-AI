# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Whisper transcription: the one pinned loader and inference path
# Issue #932: Implement actual audio transcription
# Issue #17778: the unused AudioPipeline wrapper was removed

"""The one pinned Whisper pipeline and its byte-level inference path."""

import os
import tempfile
import threading
from dataclasses import dataclass
from typing import Any

from autobot_shared.logging_manager import get_logger

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

    The one inference path (#17780). ``api/voice.py`` and the since-removed
    ``AudioPipeline`` each had their own copy of this: same model, same loader, same
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
