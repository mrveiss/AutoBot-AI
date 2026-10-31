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
import time
import wave
from dataclasses import dataclass
from typing import Any

from autobot_shared.audio_wav import wav_duration_seconds
from autobot_shared.env_utils import env_float
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
# #17778: a failed load no longer latches "unavailable" for the process lifetime --
# it is retried after WHISPER_LOAD_RETRY_SECONDS. A ModelIntegrityError is the
# exception: it is remembered and re-raised, because a tampered model must never
# degrade into "unavailable" (which callers answer by falling through to a cloud).
_whisper_pipeline: Any | None = None
_whisper_pipeline_lock = threading.Lock()
# #17778: serialises the actual pipeline INVOCATION. The one HF pipeline is shared by
# the provider, VoiceProcessor and /voice/transcribe threads, and generation mutates
# the model's generation_config, so concurrent calls would race on it.
_whisper_inference_lock = threading.Lock()
_whisper_retry_at = 0.0
_whisper_integrity_error: Exception | None = None
WHISPER_MODEL = "openai/whisper-base"
WHISPER_LOAD_RETRY_SECONDS = env_float("AUTOBOT_WHISPER_LOAD_RETRY_SECONDS", 60.0)

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


def whisper_device_kwargs() -> dict:
    """Extra ``pipeline()`` kwargs for ``AUTOBOT_WHISPER_DEVICE`` (#17778).

    ``auto`` (default): CUDA with float16 when ``torch.cuda.is_available()``,
    else ``{}``. ``cpu`` (and any unrecognised value, with a warning): ``{}`` --
    the historical CPU fp32 call, byte-identical.
    """
    from autobot_shared.env_registry import env

    choice = str(env("AUTOBOT_WHISPER_DEVICE")).strip().lower()
    if choice not in ("cpu", "auto"):
        logger.warning("AUTOBOT_WHISPER_DEVICE=%r is not cpu|auto; using cpu", choice)
        return {}
    if choice == "cpu":
        return {}
    import torch

    if not torch.cuda.is_available():
        return {}
    return {"device": "cuda", "torch_dtype": torch.float16}


def whisper_device() -> str:
    """Where Whisper actually runs: the loaded pipeline's device, else what a load would use."""
    if _whisper_pipeline is not None:
        return str(getattr(_whisper_pipeline, "device", "cpu"))
    return "cuda" if whisper_device_kwargs().get("device") else "cpu"


def whisper_loadable() -> bool:
    """Cheap, NON-loading probe: is the pinned Whisper loaded, or worth trying to load?

    Safe on the event loop: it never touches the model. False when transformers is
    missing, the model is unpinned, or a recent load failure is still inside its
    retry window. True after an integrity failure, deliberately -- the caller must
    reach :func:`get_whisper_pipeline` and see the error rather than treat a
    tampered model as merely absent.
    """
    if _whisper_pipeline is not None or _whisper_integrity_error is not None:
        return True
    if not _TRANSFORMERS_AVAILABLE or time.monotonic() < _whisper_retry_at:
        return False
    from autobot_shared.pinned_model_registry import get_pinned_revision

    try:
        get_pinned_revision(WHISPER_MODEL)
    except KeyError:
        return False
    return True


def get_whisper_pipeline() -> Any | None:
    """Lazy-load the Whisper pipeline; None if unavailable (thread-safe). BLOCKING on first use.

    Public since #17780. Call it from a worker thread (``asyncio.to_thread``), never
    on the event loop -- the first call downloads/loads the model. Use
    :func:`whisper_loadable` for a cheap availability check.

    Raises:
        ModelIntegrityError: the cached model does not match its pin. Remembered, so
            every later call raises too.
    """
    if not _TRANSFORMERS_AVAILABLE:
        return None
    if _whisper_pipeline is not None:
        return _whisper_pipeline
    with _whisper_pipeline_lock:
        if _whisper_integrity_error is not None:
            raise _whisper_integrity_error
        if _whisper_pipeline is None and time.monotonic() >= _whisper_retry_at:
            _attempt_load()
    return _whisper_pipeline


def _attempt_load() -> None:
    """One load attempt; the caller holds ``_whisper_pipeline_lock``. Records failure state."""
    global _whisper_pipeline, _whisper_retry_at, _whisper_integrity_error  # noqa: PLW0603
    try:
        # #17780: pinned and integrity-verified through `load_verified`, the
        # canonical path. #17124: assigning the model before
        # `verify_cached_model` ran left a tampered model reachable when a
        # broad `except` swallowed `ModelIntegrityError`.
        from autobot_shared.pinned_model_registry import ModelIntegrityError, load_verified

        device_kwargs = whisper_device_kwargs()
        (_whisper_pipeline,) = load_verified(
            WHISPER_MODEL,
            lambda revision: hf_pipeline(
                "automatic-speech-recognition",
                model=WHISPER_MODEL,
                revision=revision,
                **device_kwargs,
            ),
        )
        logger.info("Whisper pipeline loaded: %s on %s", WHISPER_MODEL, device_kwargs.get("device", "cpu"))
    except ModelIntegrityError as exc:
        logger.error("SECURITY: Whisper model failed its integrity check; refusing to serve: %s", exc)
        _whisper_integrity_error = exc
        raise
    except Exception as exc:
        logger.warning("Failed to load Whisper pipeline (retry in %.0fs): %s", WHISPER_LOAD_RETRY_SECONDS, exc)
        _whisper_pipeline = None
        _whisper_retry_at = time.monotonic() + WHISPER_LOAD_RETRY_SECONDS


#: Whisper's feature extractor pads/truncates to 30 s; more than 3000 mel frames
#: switches transformers to long-form generation, which REQUIRES timestamp tokens
#: (`_set_return_timestamps` in generation_whisper.py raises ValueError otherwise).
SHORT_FORM_SECONDS = 30.0


def _call_pipe(pipe: Any, inputs: Any, *, timestamps: bool, generate_kwargs: dict | None) -> WhisperTranscription:
    """One pipeline call; *timestamps* selects ``return_timestamps`` (True for long-form)."""
    with _whisper_inference_lock:
        output = pipe(inputs, return_timestamps=timestamps, generate_kwargs=generate_kwargs)
    return _as_transcription(output)


def transcribe_path(pipe: Any, path: str, *, language: str = "", timestamps: bool = False) -> WhisperTranscription:
    """Run Whisper over the audio file at *path*. BLOCKING -- call via ``asyncio.to_thread``.

    The file-taking half of :func:`transcribe_bytes`. *language* is a BCP-47 hint;
    empty means auto-detect. ``timestamps=True`` returns ``chunks`` with real
    ``timestamp`` pairs and handles any length. Without it the call keeps
    ``return_timestamps=False`` (the short-form behaviour) and retries once with
    timestamps when transformers refuses the audio as long-form (> 30 s), so the
    text of a short clip is exactly what it was and a long one no longer fails.
    The long-form choice is made from the WAV's duration, never from an error message.
    """
    generate_kwargs = {"language": language} if language else None
    seconds = _wav_seconds(path)
    if timestamps or (seconds is not None and seconds > SHORT_FORM_SECONDS):
        return _call_pipe(pipe, path, timestamps=True, generate_kwargs=generate_kwargs)
    if seconds is not None:
        return _call_pipe(pipe, path, timestamps=False, generate_kwargs=generate_kwargs)
    # A container (webm/ogg/mp3...) has no stdlib duration: try short-form, and on ANY
    # ValueError retry once long-form. If the audio was fine the retry succeeds; if the
    # error was something else the retry raises it again, so nothing is masked.
    try:
        return _call_pipe(pipe, path, timestamps=False, generate_kwargs=generate_kwargs)
    except ValueError:
        logger.info("Short-form transcription of a container raised; retrying with long-form timestamps")
        return _call_pipe(pipe, path, timestamps=True, generate_kwargs=generate_kwargs)


def _wav_seconds(path: str) -> float | None:
    """Duration of the PCM WAV at *path*, or ``None`` when it is not one (a container, or unreadable)."""
    try:
        with wave.open(path, "rb") as wav:
            return wav_duration_seconds(wav)
    except (wave.Error, EOFError, OSError):
        return None


def transcribe_array(
    pipe: Any, samples: Any, sampling_rate: int, *, generate_kwargs: dict | None = None
) -> WhisperTranscription:
    """Run Whisper over decoded *samples* (mono float array). BLOCKING (#17778).

    The ndarray input the multimodal voice processor needs. The HF pipeline accepts
    ``{"raw": array, "sampling_rate": sr}`` and resamples to the model's rate itself.
    *generate_kwargs* reach ``model.generate`` untouched (e.g. the beam settings).
    Clips of at most 30 s keep ``return_timestamps=False``; longer ones use
    long-form (``return_timestamps=True``) and the text is the joined result.
    """
    long_form = len(samples) / float(sampling_rate) > SHORT_FORM_SECONDS
    inputs = {"raw": samples, "sampling_rate": sampling_rate}
    return _call_pipe(pipe, inputs, timestamps=long_form, generate_kwargs=generate_kwargs)


def _as_transcription(output: Any) -> WhisperTranscription:
    """Shape a pipeline output; anything but a dict is empty text."""
    if not isinstance(output, dict):
        return WhisperTranscription(text="", language="unknown", chunks=[])
    return WhisperTranscription(
        text=output.get("text", "").strip(),
        language=output.get("language", "unknown"),
        chunks=output.get("chunks", []),
    )


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
        return transcribe_path(pipe, tmp_path, language=language)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
