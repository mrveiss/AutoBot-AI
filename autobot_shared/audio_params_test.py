# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""STT format constants and the WAV header reader (#17778)."""

import dataclasses
import io
import wave

import pytest

from autobot_shared.audio_params import (
    STT_CHANNELS,
    STT_SAMPLE_RATE,
    AudioFormat,
    describe_wav,
)


def _wav(*, rate: int, channels: int, width: int, frames: int = 10) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(b"\x00" * width * channels * frames)
    return buffer.getvalue()


def test_the_stt_input_format_is_16khz_mono() -> None:
    assert (STT_SAMPLE_RATE, STT_CHANNELS) == (16_000, 1)


def test_describe_wav_reads_the_header() -> None:
    fmt = describe_wav(_wav(rate=24_000, channels=1, width=2))
    assert fmt == AudioFormat(sample_rate=24_000, channels=1, sample_width=2, container="wav")


def test_describe_wav_distinguishes_rate_channels_and_width() -> None:
    fmt = describe_wav(_wav(rate=44_100, channels=2, width=3))
    assert (fmt.sample_rate, fmt.channels, fmt.sample_width) == (44_100, 2, 3)


def test_the_format_is_immutable() -> None:
    fmt = describe_wav(_wav(rate=16_000, channels=1, width=2))
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(fmt, "sample_rate", 8_000)


@pytest.mark.parametrize("payload", [b"", b"not audio at all", b"RIFF\x00\x00\x00\x00WAVE", b"ID3\x03\x00" * 8])
def test_non_wav_input_raises_value_error(payload: bytes) -> None:
    with pytest.raises(ValueError):
        describe_wav(payload)
