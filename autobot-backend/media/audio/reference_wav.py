# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Normalise a voice's reference audio to PCM mono WAV before the TTS worker sees it (#18477).

The worker reads the reference through libsndfile, which cannot decode AAC/m4a (a phone voice memo) or
other common compressed formats, so those uploads used to end as a 500. The conversion is done here with
the one bounded converter, ``media.audio.ffmpeg_service.FFmpegService`` (extension allowlist, pinned demuxer,
protocol whitelist, bounded subprocess); there is no second one.

* A WAV passes through byte-for-byte: libsndfile reads it and re-encoding would only lose quality.
* Anything else is converted. A file ffmpeg cannot decode is the CLIENT's problem: 422
  ``voice.unsupported_audio``; an extension outside the allowlist is 415 with the same code. Neither is a 500.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException

from autobot_shared.audio_params import STT_CHANNELS
from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger

from .ffmpeg_service import ALLOWED_EXTENSIONS, get_ffmpeg_service

logger = get_logger(__name__)

#: Stable machine-readable code for "this audio cannot be used as a reference".
UNSUPPORTED_AUDIO_CODE = "voice.unsupported_audio"
CONVERTER_UNAVAILABLE_CODE = "voice.converter_unavailable"

#: The reference is a short prompt; the model resamples it itself, so this only has to be above telephone quality.
REFERENCE_SAMPLE_RATE = 24_000
#: Bounds a decompression bomb: a long recording is cut, not rejected.
REFERENCE_MAX_SECONDS = env_float_clamped("AUTOBOT_VOICE_REFERENCE_MAX_SECONDS", 120.0, positive_finite=True)


def is_wav(data: bytes) -> bool:
    """RIFF/WAVE container, judged by its magic bytes and not by the client's filename."""
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def _reject(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _suffix_for(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise _reject(415, UNSUPPORTED_AUDIO_CODE, f"Audio type '{suffix or 'unknown'}' is not supported")
    return suffix


async def _convert(data: bytes, suffix: str) -> bytes:
    src = tempfile.NamedTemporaryFile(suffix=suffix, prefix="voice_ref_", delete=False)  # noqa: SIM115
    out_path = None
    try:
        with src:
            src.write(data)
        out_path = await get_ffmpeg_service().extract_audio(
            src.name, sample_rate=REFERENCE_SAMPLE_RATE, channels=STT_CHANNELS, max_duration=REFERENCE_MAX_SECONDS
        )
        return await asyncio.to_thread(Path(out_path).read_bytes)
    finally:
        for path in (src.name, out_path):
            if path and os.path.exists(path):
                os.unlink(path)


async def to_reference_wav(data: bytes, filename: str | None) -> bytes:
    """*data* as WAV bytes the worker can read; raises an HTTP 4xx (never a 500) for audio that cannot be used."""
    if is_wav(data):
        return data
    suffix = _suffix_for(filename)
    try:
        wav = await _convert(data, suffix)
    except RuntimeError as exc:
        if str(exc).startswith("FFmpeg not found"):
            logger.error("Voice reference conversion unavailable: %s", exc)
            raise _reject(503, CONVERTER_UNAVAILABLE_CODE, "Audio conversion is not available on this server") from exc
        logger.warning("Voice reference audio could not be decoded: %s", str(exc)[-300:])
        raise _reject(422, UNSUPPORTED_AUDIO_CODE, "The audio could not be decoded") from exc
    if not is_wav(wav):
        raise _reject(422, UNSUPPORTED_AUDIO_CODE, "The audio could not be decoded")
    return wav
