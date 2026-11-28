# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The shared WAV duration helper (#13841)."""

import io
import wave

from autobot_shared.audio_wav import wav_duration_seconds


def _wav(*, frames: int, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate if rate > 0 else 8000)
        out.writeframes(b"\x00\x00" * frames)
    payload = bytearray(buffer.getvalue())
    if rate <= 0:
        # Patch the sample-rate field directly: `wave` refuses to WRITE a bad
        # rate, and a malformed header is exactly the case the guard exists for.
        payload[24:28] = rate.to_bytes(4, "little", signed=True) if rate >= 0 else (0).to_bytes(4, "little")
    return bytes(payload)


def test_duration_is_frames_over_rate() -> None:
    with wave.open(io.BytesIO(_wav(frames=16000, rate=16000)), "rb") as wav:
        assert wav_duration_seconds(wav) == 1.0


def test_a_fractional_duration_is_not_rounded() -> None:
    """Throughput sums many short chunks; rounding each one would drift the total."""
    with wave.open(io.BytesIO(_wav(frames=8000, rate=16000)), "rb") as wav:
        assert wav_duration_seconds(wav) == 0.5


def test_an_empty_payload_is_zero_not_an_error() -> None:
    with wave.open(io.BytesIO(_wav(frames=0, rate=16000)), "rb") as wav:
        assert wav_duration_seconds(wav) == 0.0


def test_a_zero_frame_rate_returns_zero_rather_than_raising() -> None:
    """The guard's whole purpose: a malformed header must not raise into a caller
    that is measuring something incidental to its real job."""
    with wave.open(io.BytesIO(_wav(frames=1000, rate=0)), "rb") as wav:
        assert wav_duration_seconds(wav) == 0.0
