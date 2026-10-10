# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Speech Provider Registry

Language-keyed speech provider system for multi-language transcription.
Part of Issue #9044 (MVA-2154 parent).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.pinned_model_registry import ModelIntegrityError

logger = get_logger(__name__)


@dataclass
class TranscriptSegment:
    """Transcription segment with timing information."""

    text: str
    start_time: float
    end_time: float
    confidence: float
    language: Optional[str] = None
    speaker: Optional[str] = None


class SpeechProvider(ABC):
    """Base interface for speech recognition providers."""

    @abstractmethod
    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> List[TranscriptSegment]:
        """Transcribe audio file to segments.

        Args:
            audio_path: Path to audio file
            language: Optional language hint (BCP-47 code like 'lv', 'en')

        Returns:
            List of transcript segments with timing
        """

    def is_available(self) -> bool:
        """Whether the provider can transcribe right now (default: yes).

        A provider that depends on something loadable (a model, a binary) overrides
        this so :meth:`ProviderRegistry.transcribe_with_fallback` can skip it.
        """
        return True

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider name for logging/debugging."""

    @property
    @abstractmethod
    def supported_languages(self) -> List[str]:
        """Return list of supported language codes."""


#: Errors the fallback loop re-raises instead of trying the next provider: a tampered
#: model must not degrade to a cloud provider, and a programming error is not a
#: provider outage.
_NEVER_FALL_THROUGH = (ModelIntegrityError, TypeError, AttributeError, NameError)


class TranscriptionUnavailableError(RuntimeError):
    """No provider produced a transcript and at least one could not run or raised."""

    def __init__(self, language: str, reasons: List[str]):
        self.language = language
        self.reasons = list(reasons)
        super().__init__(f"No speech provider could transcribe language {language!r}: " + "; ".join(self.reasons))


@dataclass
class ProviderTranscription:
    """The provider that produced *segments*; ``provider`` is None when none did."""

    provider: Optional[SpeechProvider]
    segments: List[TranscriptSegment]


class ProviderRegistry:
    """Registry for language-keyed speech providers."""

    def __init__(self):
        """Initialize empty provider registry."""
        self._providers: Dict[str, List[SpeechProvider]] = {}

    def register(self, language: str, provider: SpeechProvider, priority: int = 0):
        """Register a provider for a language.

        Args:
            language: BCP-47 language code (e.g., 'lv', 'en')
            provider: Speech provider instance
            priority: Higher priority providers tried first (default 0)
        """
        if language not in self._providers:
            self._providers[language] = []

        # Insert by priority (higher first)
        providers = self._providers[language]
        insert_idx = 0
        for i, (p, prio) in enumerate(providers):
            if priority > prio:
                insert_idx = i
                break
            insert_idx = i + 1

        providers.insert(insert_idx, (provider, priority))
        logger.info(f"Registered {provider.provider_name} for language '{language}' " f"with priority {priority}")

    def get_provider(self, language: str) -> Optional[SpeechProvider]:
        """Get highest-priority provider for a language.

        Args:
            language: BCP-47 language code

        Returns:
            Provider instance or None if no provider registered
        """
        providers = self._providers.get(language)
        if not providers:
            logger.warning(f"No provider registered for language: {language}")
            return None

        # Return highest priority (first in list)
        provider, priority = providers[0]
        logger.debug(f"Selected {provider.provider_name} for language '{language}' " f"(priority {priority})")
        return provider

    def get_all_providers(self, language: str) -> List[SpeechProvider]:
        """Get all providers for a language, ordered by priority.

        Args:
            language: BCP-47 language code

        Returns:
            List of provider instances (highest priority first)
        """
        providers = self._providers.get(language, [])
        return [p for p, _ in providers]

    async def transcribe_with_fallback(self, audio_path: str, language: str) -> ProviderTranscription:
        """Try every provider for *language* in priority order (Issue #17778).

        The ONE fallback loop: a provider that is unavailable, raises, or returns no
        segments hands over to the next. Two very different "no segments" outcomes:

        * every provider RAN and found no speech -> ``ProviderTranscription(None, [])``,
          a genuine empty transcript;
        * a provider could not run or raised, and none produced segments ->
          :class:`TranscriptionUnavailableError` carrying every reason.

        Raises:
            ValueError: no provider is registered for *language*.
            TranscriptionUnavailableError: see above.
            ModelIntegrityError, TypeError, AttributeError, NameError: propagated at
                once. An integrity failure must never fall through to an external
                provider, and a programming error must not be disguised as "provider
                failed".
        """
        providers = self.get_all_providers(language)
        if not providers:
            raise ValueError(f"No speech provider available for language: {language}")
        reasons: List[str] = []
        for provider in providers:
            segments = await self._attempt(provider, audio_path, language, reasons)
            if segments:
                return ProviderTranscription(provider, segments)
        if reasons:
            raise TranscriptionUnavailableError(language, reasons)
        return ProviderTranscription(None, [])

    @staticmethod
    async def _attempt(
        provider: SpeechProvider, audio_path: str, language: str, reasons: List[str]
    ) -> List[TranscriptSegment]:
        """One provider's attempt; appends to *reasons* when it could not run or raised."""
        name = provider.provider_name
        if not provider.is_available():
            logger.info("Provider %s unavailable; falling through", name)
            reasons.append(f"{name}: unavailable")
            return []
        logger.info("Transcribing with %s (lang=%s)", name, language)
        try:
            return await provider.transcribe(audio_path, language) or []
        except _NEVER_FALL_THROUGH:
            logger.error("Provider %s failed with an error that must not fall through", name, exc_info=True)
            raise
        except Exception as exc:
            logger.warning("Provider %s failed for %r: %s", name, language, exc, exc_info=True)
            reasons.append(f"{name}: {type(exc).__name__}")
            return []

    def languages(self) -> List[str]:
        """Return the language codes that have at least one registered provider."""
        return list(self._providers.keys())


# Global registry instance
_registry = ProviderRegistry()


def get_speech_provider_registry() -> ProviderRegistry:
    """Get global speech provider registry instance."""
    return _registry


def get_speech_provider(language: str) -> Optional[SpeechProvider]:
    """Convenience function to get provider for a language.

    Args:
        language: BCP-47 language code (e.g., 'lv', 'en')

    Returns:
        Provider instance or None if no provider for this language
    """
    return _registry.get_provider(language)
