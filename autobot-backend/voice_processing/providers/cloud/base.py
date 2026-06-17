# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Cloud Speech Provider base class (Issue #10147).

All cloud ASR adapters extend CloudSpeechProvider which:
- Reads an API key from an env var (fail-soft when absent)
- Sets diarizes=True so the orchestrator can skip local Pyannote
- Provides shared aiohttp session helpers
"""

import os
from abc import abstractmethod
from typing import List, Optional

import aiohttp

from autobot_shared.logging_manager import get_logger
from voice_processing.providers import SpeechProvider, TranscriptSegment

logger = get_logger(__name__)

_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=600, connect=30)


class CloudSpeechProvider(SpeechProvider):
    """Base for cloud ASR providers that return speaker-diarized segments.

    Privacy note: audio is sent off-box to a third-party API. This tier is
    opt-in — a provider is only registered when its API key is present.
    """

    #: env var name that holds the API key for this provider
    _api_key_env: str = ""

    #: cloud providers always return speaker labels
    diarizes: bool = True

    def __init__(self) -> None:
        self._api_key: Optional[str] = os.environ.get(self._api_key_env) if self._api_key_env else None
        if not self._api_key:
            logger.warning(
                "%s: %s not set — provider unconfigured. " "Set the env var to enable this cloud ASR provider.",
                self.__class__.__name__,
                self._api_key_env,
            )

    @property
    def is_configured(self) -> bool:
        """True when the API key is present in the environment."""
        return bool(self._api_key)

    @abstractmethod
    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> List[TranscriptSegment]:
        """Transcribe audio; return segments with .speaker set."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name."""

    @property
    @abstractmethod
    def supported_languages(self) -> List[str]:
        """BCP-47 language codes this provider supports."""

    # ── shared helpers ────────────────────────────────────────────────────────

    def _make_session(self, timeout: Optional[aiohttp.ClientTimeout] = None) -> aiohttp.ClientSession:
        """Return a new aiohttp session with sensible defaults."""
        return aiohttp.ClientSession(timeout=timeout or _DEFAULT_TIMEOUT)

    def _auth_header(self) -> str:
        """Return 'Bearer <key>' auth header value."""
        return f"Bearer {self._api_key}"
