# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Decode uploaded audio container bytes to the STT input format (#17778).

``POST /multimodal/audio`` hands the processor the *file's* bytes (WAV, webm, ...).
Reading those as raw float32 samples -- which ``VoiceProcessor`` did -- feeds the
container header and compressed payload to Whisper as if it were a waveform, so
the upload was transcribed as noise. This decodes to what the models expect:
mono float32 at ``STT_SAMPLE_RATE``.

PCM WAV (8/16/24/32-bit) is decoded here with the stdlib. Every other container --
including the webm/matroska a browser ``MediaRecorder`` produces -- is first
converted to a 16 kHz mono PCM WAV by the existing hardened
:class:`~media.audio.ffmpeg_service.FFmpegService`, then takes the same WAV path.
"""

from __future__ import annotations

import asyncio
import io
import math
import os
import tempfile
import wave

import numpy as np

from autobot_shared.audio_params import STT_CHANNELS, STT_SAMPLE_RATE, AudioFormat, describe_wav
from autobot_shared.env_registry import env
from autobot_shared.logging_manager import get_logger
from media.audio.ffmpeg_service import get_ffmpeg_service

logger = get_logger(__name__)

#: What the caller is told when bytes cannot be decoded -- never a raw library message.
UNDECODABLE_MESSAGE = "Unsupported or unreadable audio format"

#: Container magic -> temp-file suffix (must be in the ffmpeg service's allowlist).
_MAGIC = (
    (b"\x1a\x45\xdf\xa3", 0, ".webm"),
    (b"OggS", 0, ".ogg"),
    (b"fLaC", 0, ".flac"),
    (b"ID3", 0, ".mp3"),
    (b"\xff\xfb", 0, ".mp3"),
    (b"ftyp", 4, ".m4a"),
)

#: ffmpeg writes ``pcm_s16le``: 2 bytes per sample.
_DECODED_SAMPLE_BYTES = 2

_INT_DTYPES = {1: (np.uint8, 128.0, 128.0), 2: (np.int16, 0.0, 32768.0), 4: (np.int32, 0.0, 2147483648.0)}


class NotPcmWavError(ValueError):
    """The bytes are not a PCM WAV this module decodes itself; they need transcoding."""


def decode_audio_bytes(data: bytes, target_rate: int = STT_SAMPLE_RATE) -> np.ndarray:
    """Decode PCM WAV *data* to mono float32 at *target_rate* (synchronous).

    Raises :class:`NotPcmWavError` for anything else; use
    :func:`decode_audio_bytes_async` to accept any container.
    """
    try:
        fmt = describe_wav(data)
    except ValueError as exc:
        raise NotPcmWavError(UNDECODABLE_MESSAGE) from exc
    if fmt.sample_rate <= 0 or fmt.channels <= 0 or fmt.sample_width not in (1, 2, 3, 4):
        raise NotPcmWavError(UNDECODABLE_MESSAGE)
    return _decode_pcm_wav(data, fmt, target_rate)


async def decode_audio_bytes_async(data: bytes, target_rate: int = STT_SAMPLE_RATE) -> np.ndarray:
    """Decode any supported container to mono float32 at *target_rate*; ``ValueError`` otherwise."""
    try:
        return await asyncio.to_thread(decode_audio_bytes, data, target_rate)
    except NotPcmWavError:
        pass
    return await _transcode_then_decode(data, target_rate)


async def _transcode_then_decode(data: bytes, target_rate: int) -> np.ndarray:
    """ffmpeg -> 16 kHz mono PCM WAV in a temp file -> the stdlib WAV path."""
    suffix = _sniff_suffix(data)
    in_fd, in_path = tempfile.mkstemp(suffix=suffix, prefix="upload_")
    out_fd, out_path = tempfile.mkstemp(suffix=".wav", prefix="decoded_")
    os.close(out_fd)
    try:
        with os.fdopen(in_fd, "wb") as fh:
            fh.write(data)
        max_seconds = float(env("AUTOBOT_AUDIO_DECODE_MAX_SECONDS"))
        await get_ffmpeg_service().extract_audio(
            in_path,
            out_path,
            sample_rate=target_rate,
            channels=STT_CHANNELS,
            max_duration=max_seconds + 1.0,  # one second of slack: longer output means "too long", not "cut"
        )
        _check_output_bounds(out_path, target_rate, max_seconds)
        with open(out_path, "rb") as fh:
            wav_bytes = fh.read()
        return await asyncio.to_thread(decode_audio_bytes, wav_bytes, target_rate)
    except (RuntimeError, OSError, ValueError, asyncio.TimeoutError) as exc:
        logger.warning("Audio transcode failed (%s): %s", suffix, exc, exc_info=True)
        raise ValueError(UNDECODABLE_MESSAGE) from None
    finally:
        for path in (in_path, out_path):
            try:
                os.unlink(path)
            except OSError:
                pass


def _check_output_bounds(out_path: str, target_rate: int, max_seconds: float) -> None:
    """Refuse a transcoded WAV over the byte cap or longer than *max_seconds*, before reading it."""
    size = os.stat(out_path).st_size
    byte_cap = int(env("AUTOBOT_AUDIO_DECODE_MAX_OUTPUT_BYTES"))
    if size > byte_cap:
        raise ValueError(f"Decoded audio is {size} bytes, over the {byte_cap}-byte cap")
    seconds = size / (target_rate * STT_CHANNELS * _DECODED_SAMPLE_BYTES)
    if seconds > max_seconds:
        raise ValueError(f"Decoded audio is {seconds:.0f}s, over the {max_seconds:.0f}s cap")


def _sniff_suffix(data: bytes) -> str:
    """Temp-file suffix for the container *data* appears to be; ``ValueError`` if unknown."""
    for magic, offset, suffix in _MAGIC:
        if data[offset : offset + len(magic)] == magic:
            return suffix
    raise ValueError(UNDECODABLE_MESSAGE)


def _to_float(raw: bytes, width: int) -> np.ndarray:
    """Interleaved PCM bytes -> float64 samples in [-1, 1)."""
    if width == 3:  # no numpy 24-bit dtype: assemble little-endian, sign-extend
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        value = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        return ((value ^ 0x800000) - 0x800000) / 8388608.0
    dtype, offset, scale = _INT_DTYPES[width]
    return (np.frombuffer(raw, dtype=dtype).astype(np.float64) - offset) / scale


def _decode_pcm_wav(data: bytes, fmt: AudioFormat, target_rate: int) -> np.ndarray:
    """PCM WAV -> mono float32 in [-1, 1], resampled to *target_rate*."""
    with wave.open(io.BytesIO(data), "rb") as wav:
        raw = wav.readframes(wav.getnframes())
    frame_bytes = fmt.sample_width * fmt.channels
    samples = _to_float(raw[: len(raw) - len(raw) % frame_bytes], fmt.sample_width)
    mono = samples.reshape(-1, fmt.channels).mean(axis=1)
    return _resample(mono, fmt.sample_rate, target_rate).astype(np.float32)


def _resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Polyphase resample (anti-aliased); a no-op when the rates already match."""
    if source_rate == target_rate or samples.size == 0:
        return samples
    from scipy.signal import resample_poly

    divisor = math.gcd(source_rate, target_rate)
    return resample_poly(samples, target_rate // divisor, source_rate // divisor)
