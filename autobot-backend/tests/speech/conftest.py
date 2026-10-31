# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared fixtures for the speech characterization suite (#17778).

These tests pin the audio parameters the tree uses TODAY, so a later slice that
consolidates the speech forks cannot change what a user hears without a test
reddening. Nothing here asserts what the parameters SHOULD be.
"""

import io
import wave
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

from testkit.module_stubs import StubSet

_PERSONALITY_PATH = Path(__file__).resolve().parents[2] / "services" / "personality_service.py"
_PRIVATE_NAME = "_speech_17778_personality_service"


def build_wav(rate: int = 24_000, channels: int = 1, width: int = 2, frames: int = 240) -> bytes:
    """A silent PCM WAV built with the stdlib ``wave`` module.

    The default (24 kHz, not 16 kHz) is deliberately not the STT format, so a test
    that confuses "what the synthesiser emitted" with "what STT wants" fails
    instead of passing by coincidence.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(b"\x00" * width * channels * frames)
    return buffer.getvalue()


@pytest.fixture
def make_wav() -> Callable[..., bytes]:
    return build_wav


@pytest.fixture
def fixture_wav() -> bytes:
    """The fixture WAV every TTS-side test feeds the code under test."""
    return build_wav()


@pytest.fixture
def real_personality_service() -> Iterator[ModuleType]:
    """The real ``services.personality_service``, loaded under a private name.

    The backend conftest registers a stub for that module (it only needs
    ``SUPPORTED_LANGUAGES``), so a plain import yields a MagicMock and
    ``resolve_voice_id`` could not be exercised. The stub is left in place for
    everyone else; this loads the file separately through ``StubSet.real_load``
    and registers it in ``sys.modules`` only for the duration of one test
    (``restore`` puts the previous state back), which keeps dataclass annotation
    lookup working.
    """
    stubs = StubSet()
    try:
        module = stubs.real_load(_PRIVATE_NAME, _PERSONALITY_PATH, reuse_if_loaded=False)
        assert module is not None
        yield module
    finally:
        stubs.restore()
