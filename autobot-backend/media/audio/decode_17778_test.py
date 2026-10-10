# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Uploaded audio containers decode to real samples, not float32 noise (#17778)."""

import io
import math
import struct
import wave

import numpy as np
import pytest

from autobot_shared.audio_params import STT_SAMPLE_RATE
from media.audio.decode import decode_audio_bytes

SOURCE_RATE, SECONDS, FREQ_HZ, PEAK = 22_050, 1.0, 440, 12_000


def _sine_wav(channels: int = 2, width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(SOURCE_RATE)
        for i in range(int(SOURCE_RATE * SECONDS)):
            sample = int(PEAK * math.sin(2 * math.pi * FREQ_HZ * i / SOURCE_RATE))
            wav.writeframes(struct.pack("<h", sample) * channels)
    return buf.getvalue()


def _dominant_hz(samples: np.ndarray, rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(samples))
    return float(np.argmax(spectrum) * rate / len(samples))


def test_stereo_22k_wav_becomes_mono_16k_with_the_right_length_and_amplitude():
    samples = decode_audio_bytes(_sine_wav())
    assert samples.dtype == np.float32 and samples.ndim == 1
    assert len(samples) == pytest.approx(STT_SAMPLE_RATE * SECONDS, abs=2)
    assert float(np.abs(samples).max()) == pytest.approx(PEAK / 32768, abs=0.02)


def test_decoded_signal_is_the_tone_that_was_encoded():
    samples = decode_audio_bytes(_sine_wav())
    assert _dominant_hz(samples, STT_SAMPLE_RATE) == pytest.approx(FREQ_HZ, abs=2)


def test_the_old_float32_reinterpretation_is_not_a_waveform():
    """What the processor used to do with these bytes, to show the contrast."""
    data = _sine_wav()
    garbage = np.frombuffer(data[: len(data) - len(data) % 4], dtype=np.float32)
    assert len(garbage) != STT_SAMPLE_RATE, "the length only matches by accident of decoding"
    finite = garbage[np.isfinite(garbage)]
    assert finite.size and abs(_dominant_hz(finite, SOURCE_RATE) - FREQ_HZ) > 50


def test_matching_rate_mono_wav_is_not_resampled():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(STT_SAMPLE_RATE)
        wav.writeframes(np.array([0, 16384, -16384], dtype="<i2").tobytes())
    np.testing.assert_allclose(decode_audio_bytes(buf.getvalue()), [0.0, 0.5, -0.5])


def test_undecodable_bytes_raise_value_error():
    with pytest.raises(ValueError):
        decode_audio_bytes(b"definitely not audio")
