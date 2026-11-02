# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Uploaded audio containers decode to real samples, not float32 noise (#17778)."""

import io
import math
import shutil
import struct
import subprocess
import wave

import numpy as np
import pytest

from autobot_shared.audio_params import STT_SAMPLE_RATE
from media.audio.decode import NotPcmWavError, decode_audio_bytes, decode_audio_bytes_async

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


def _wav(width: int, frames: list[int], rate: int = STT_SAMPLE_RATE) -> bytes:
    """Mono PCM WAV of *width* bytes; *frames* are already in that width's integer range."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        packed = b"".join(int(v).to_bytes(width, "little", signed=width != 1) for v in frames)
        wav.writeframes(packed)
    return buf.getvalue()


def test_8_bit_unsigned_wav_is_centred_on_128():
    np.testing.assert_allclose(decode_audio_bytes(_wav(1, [128, 255, 0])), [0.0, 127 / 128, -1.0], atol=1e-6)


def test_24_bit_wav_keeps_sign_and_scale():
    half = 1 << 22
    np.testing.assert_allclose(decode_audio_bytes(_wav(3, [0, half, -half])), [0.0, 0.5, -0.5], atol=1e-6)


def test_32_bit_wav_keeps_sign_and_scale():
    half = 1 << 30
    np.testing.assert_allclose(decode_audio_bytes(_wav(4, [0, half, -half])), [0.0, 0.5, -0.5], atol=1e-6)


def test_a_zero_sample_rate_header_is_refused_not_divided_by():
    data = bytearray(_wav(2, [0, 1, 2]))
    data[24:28] = (0).to_bytes(4, "little")  # frame rate field of the fmt chunk
    with pytest.raises(NotPcmWavError):
        decode_audio_bytes(bytes(data))


def test_non_wav_bytes_say_so_without_a_library_message():
    with pytest.raises(ValueError) as caught:
        decode_audio_bytes(b"definitely not audio")
    assert str(caught.value) == "Unsupported or unreadable audio format"


_needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg binary not installed")


def _ffmpeg_fixture(codec: str, fmt: str) -> bytes:
    """2 s of a 440 Hz tone encoded by the local ffmpeg (what a browser recorder would send)."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    return subprocess.run([*cmd, "-c:a", codec, "-f", fmt, "pipe:1"], check=True, capture_output=True).stdout


@_needs_ffmpeg
@pytest.mark.asyncio
@pytest.mark.parametrize("codec, fmt", [("libopus", "webm"), ("libvorbis", "ogg")])
async def test_browser_containers_are_transcoded_then_decoded(codec, fmt):
    samples = await decode_audio_bytes_async(_ffmpeg_fixture(codec, fmt))
    assert samples.dtype == np.float32
    assert len(samples) == pytest.approx(2 * STT_SAMPLE_RATE, rel=0.05)
    assert _dominant_hz(samples, STT_SAMPLE_RATE) == pytest.approx(FREQ_HZ, abs=5)


@pytest.mark.asyncio
async def test_undecodable_upload_gets_the_sanitised_message():
    with pytest.raises(ValueError) as caught:
        await decode_audio_bytes_async(b"\x1a\x45\xdf\xa3 not really matroska")
    assert str(caught.value) == "Unsupported or unreadable audio format"
