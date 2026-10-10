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

PCM WAV is decoded here with the stdlib; every other container goes to librosa
(the declared media dependency, already required by the path-input branch).
"""

from __future__ import annotations

import io
import math
import wave

import numpy as np

from autobot_shared.audio_params import STT_SAMPLE_RATE, AudioFormat, describe_wav

#: bytes-per-sample -> (numpy dtype, zero offset, full-scale divisor) for PCM WAV.
_PCM = {
    1: (np.uint8, 128.0, 128.0),
    2: (np.int16, 0.0, 32768.0),
    4: (np.int32, 0.0, 2147483648.0),
}


def decode_audio_bytes(data: bytes, target_rate: int = STT_SAMPLE_RATE) -> np.ndarray:
    """Return *data* (a WAV/webm/ogg/... file's bytes) as mono float32 at *target_rate*.

    Raises ``ValueError`` when the bytes are not decodable audio.
    """
    try:
        fmt = describe_wav(data)
    except ValueError:
        return _decode_with_librosa(data, target_rate)
    if fmt.sample_width not in _PCM:
        return _decode_with_librosa(data, target_rate)
    return _decode_pcm_wav(data, fmt, target_rate)


def _decode_pcm_wav(data: bytes, fmt: AudioFormat, target_rate: int) -> np.ndarray:
    """PCM WAV -> mono float32 in [-1, 1], resampled to *target_rate*."""
    dtype, offset, scale = _PCM[fmt.sample_width]
    with wave.open(io.BytesIO(data), "rb") as wav:
        raw = np.frombuffer(wav.readframes(wav.getnframes()), dtype=dtype)
    frames = raw[: len(raw) - len(raw) % fmt.channels].reshape(-1, fmt.channels)
    mono = ((frames.astype(np.float64) - offset) / scale).mean(axis=1)
    return _resample(mono, fmt.sample_rate, target_rate).astype(np.float32)


def _resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Polyphase resample (anti-aliased); a no-op when the rates already match."""
    if source_rate == target_rate or samples.size == 0:
        return samples
    from scipy.signal import resample_poly

    divisor = math.gcd(source_rate, target_rate)
    return resample_poly(samples, target_rate // divisor, source_rate // divisor)


def _decode_with_librosa(data: bytes, target_rate: int) -> np.ndarray:
    """Any other container via librosa; ``ValueError`` if it cannot be decoded."""
    try:
        import librosa
    except ImportError as exc:
        raise ValueError("cannot decode this audio container: librosa is not installed") from exc
    try:
        samples, _ = librosa.load(io.BytesIO(data), sr=target_rate, mono=True)
    except Exception as exc:
        raise ValueError(f"not decodable audio: {exc}") from exc
    return samples.astype(np.float32)
