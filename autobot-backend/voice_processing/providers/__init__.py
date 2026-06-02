# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider name for logging/debugging."""
        pass

    @property
    @abstractmethod
    def supported_languages(self) -> List[str]:
        """Return list of supported language codes."""
        pass


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
