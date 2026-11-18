# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one owner of the speech-to-text input format, and a WAV header reader (#17778).

Whisper-family models are trained on 16 kHz mono audio. That fact is written as a
bare ``16000`` at several call sites (ffmpeg normalisation, the multimodal voice
processor, the librosa loader); this module names it once so a later slice can
adopt the name at each site. Nothing imports these constants yet -- adoption is
deliberately a separate step, so introducing the owner cannot change what anyone
hears.

``describe_wav`` answers "what format is this payload?" from the header alone, so
a test (or a guard) can compare what a synthesiser actually emitted against what
a consumer assumes, instead of each re-deriving it with its own ``wave`` calls.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass

#: Sample rate (Hz) Whisper/STT models expect as input.
STT_SAMPLE_RATE = 16_000

#: Channel count STT models expect as input (mono).
STT_CHANNELS = 1

_WAV_CONTAINER = "wav"


@dataclass(frozen=True)
class AudioFormat:
    """The PCM parameters of an audio payload, as its container header states them."""

    sample_rate: int
    channels: int
    sample_width: int
    container: str


def describe_wav(data: bytes) -> AudioFormat:
    """Read the format of WAV *data* from its header. Raises ``ValueError`` if not WAV.

    ``sample_width`` is in bytes per sample (2 for 16-bit PCM). The stdlib
    ``wave`` module reports malformed input as ``wave.Error`` or ``EOFError``;
    both are folded into ``ValueError`` so callers handle one exception type.
    """
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            return AudioFormat(
                sample_rate=wav.getframerate(),
                channels=wav.getnchannels(),
                sample_width=wav.getsampwidth(),
                container=_WAV_CONTAINER,
            )
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"not a readable WAV payload: {exc}") from exc
