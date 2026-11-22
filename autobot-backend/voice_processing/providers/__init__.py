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
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional

from autobot_shared.env_registry import env
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

    #: True when the audio leaves this host (cloud ASR, Tilde, recognize_google). The
    #: fallback loop never hands audio to a second external provider by default.
    is_external: bool = False

    #: True for the one owner-decided fallthrough (#17781 AC3): the provider may take
    #: over, even though external, once the local default (Whisper) was UNAVAILABLE.
    external_when_local_unavailable: bool = False

    #: True for the local default whose UNAVAILABILITY unlocks that exception (Whisper).
    is_default_local: bool = False

    def is_available(self) -> bool:
        """Whether the provider can transcribe right now (default: yes).

        A provider that depends on something loadable (a model, a binary) overrides
        this so :meth:`SpeechProviderRegistry.transcribe_with_fallback` can skip it.
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


_RAN, _UNAVAILABLE, _RAISED = "ran", "unavailable", "raised"


def _may_fall_through(
    candidate: SpeechProvider,
    local_unavailable: bool,
    local_failed: bool = False,
    primary: bool = False,
    external_attempted: bool = False,
) -> bool:
    """Whether a later *candidate* may receive audio after an earlier provider could not run.

    *primary*: the candidate is the language's declared primary external provider; it may take
    over once a local engine of that chain was unavailable or raised (*local_failed*).
    Both exceptions apply only while no external provider has been ATTEMPTED in this chain
    (*external_attempted*): audio that already reached one third party never reaches a second
    without ``AUTOBOT_SPEECH_EXTERNAL_FALLTHROUGH``.
    """
    if not candidate.is_external:
        return True
    if env("AUTOBOT_SPEECH_EXTERNAL_FALLTHROUGH"):
        return True
    if external_attempted:
        return False
    if primary and local_failed:
        return True
    return candidate.external_when_local_unavailable and local_unavailable


class ProviderFailed(RuntimeError):
    """A provider could not produce a transcript: an HTTP/auth error, timeout, bad output.

    The contract every provider keeps (#17778): RAISE this (or :class:`ProviderUnavailable`)
    on failure and return ``[]`` ONLY for a successful call that found no speech. The
    fallback chain treats a returned ``[]`` as "ran, heard nothing" and stops there, so a
    failure disguised as ``[]`` silently ends the chain with an empty transcript.
    """


class ProviderUnavailable(ProviderFailed):
    """A dependency, binary, credential or API key the provider needs is missing."""


@contextmanager
def failures_as_provider_failed(name: str) -> Iterator[None]:
    """Re-raise any operational error in the body as :class:`ProviderFailed`.

    Typed errors pass through unchanged, as do the programming errors and integrity
    failures the chain must never disguise (``_NEVER_FALL_THROUGH``). The one place
    providers translate failures, so none raises an ad-hoc exception type.
    """
    try:
        yield
    except (ProviderFailed, *_NEVER_FALL_THROUGH):
        raise
    except Exception as exc:
        raise ProviderFailed(f"{name} failed: {type(exc).__name__}: {exc}") from exc


class TranscriptionUnavailableError(RuntimeError):
    """No provider produced a transcript and at least one could not run or raised."""

    def __init__(self, language: str, reasons: List[str]):
        self.language = language
        self.reasons = list(reasons)
        super().__init__(f"No speech provider could transcribe language {language!r}: " + "; ".join(self.reasons))


@dataclass
class ProviderTranscription:
    """The provider that RAN and produced *segments* (possibly none: no speech)."""

    provider: Optional[SpeechProvider]
    segments: List[TranscriptSegment]


class SpeechProviderRegistry:
    """Registry for language-keyed speech providers."""

    def __init__(self):
        """Initialize empty provider registry."""
        self._providers: Dict[str, List[SpeechProvider]] = {}
        self._primary_external: Dict[str, SpeechProvider] = {}

    def declare_primary_external(self, language: str, provider: SpeechProvider) -> None:
        """Declare *provider* the primary external provider of *language* (owner decision, #17778).

        It alone may receive audio after the language's local engine is unavailable or raised,
        without ``AUTOBOT_SPEECH_EXTERNAL_FALLTHROUGH``. Declared once, beside the chain's registration.
        """
        self._primary_external[language] = provider

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
        """Transcribe with the first provider that RUNS for *language* (Issues #17778, #17781).

        Fall through ONLY when a provider is unavailable or raised; the first provider
        that ran ends the chain, an empty result (no speech) included, so the same audio
        is never replayed to another party. Beyond that, audio is never handed to a
        non-selected EXTERNAL provider unless ``AUTOBOT_SPEECH_EXTERNAL_FALLTHROUGH`` is
        on. A failed selected cloud therefore goes to local providers (Whisper) and
        stops. The one owner-decided exception is Generic when Whisper is UNAVAILABLE
        (:attr:`SpeechProvider.external_when_local_unavailable`, #17781 AC3), and a language's
        declared primary external provider (:meth:`declare_primary_external`, Latvian -> Tilde)
        once its local engine failed.

        Returns ``ProviderTranscription(provider, segments)``; ``provider`` is the one
        that ran (segments may be empty: a genuine empty transcript).

        Raises:
            ValueError: no provider is registered for *language*.
            TranscriptionUnavailableError: nothing ran; carries every reason.
            ModelIntegrityError, TypeError, AttributeError, NameError: propagated at
                once, never disguised as a provider failure.
        """
        providers = self.get_all_providers(language)
        if not providers:
            raise ValueError(f"No speech provider available for language: {language}")
        reasons: List[str] = []
        local_unavailable = local_failed = external_attempted = False
        primary = self._primary_external.get(language)
        for index, provider in enumerate(providers):
            if index and not _may_fall_through(
                provider, local_unavailable, local_failed, provider is primary, external_attempted
            ):
                reasons.append(f"{provider.provider_name}: external fallthrough refused")
                continue
            status, segments = await self._attempt(provider, audio_path, language, reasons)
            if status == _RAN:
                return ProviderTranscription(provider, segments)
            local_unavailable = local_unavailable or (status == _UNAVAILABLE and provider.is_default_local)
            local_failed = local_failed or not provider.is_external
            external_attempted = external_attempted or (provider.is_external and status != _UNAVAILABLE)
        raise TranscriptionUnavailableError(language, reasons)

    @staticmethod
    async def _attempt(
        provider: SpeechProvider, audio_path: str, language: str, reasons: List[str]
    ) -> tuple[str, List[TranscriptSegment]]:
        """One attempt as ``(status, segments)``; appends to *reasons* when it could not run or raised."""
        name = provider.provider_name
        if not provider.is_available():
            logger.info("Provider %s unavailable; falling through", name)
            reasons.append(f"{name}: unavailable")
            return _UNAVAILABLE, []
        logger.info("Transcribing with %s (lang=%s)", name, language)
        try:
            return _RAN, await provider.transcribe(audio_path, language) or []
        except _NEVER_FALL_THROUGH:
            logger.error("Provider %s failed with an error that must not fall through", name, exc_info=True)
            raise
        except Exception as exc:
            logger.warning("Provider %s failed for %r: %s", name, language, exc, exc_info=True)
            reasons.append(f"{name}: {type(exc).__name__}")
            return _RAISED, []

    def languages(self) -> List[str]:
        """Return the language codes that have at least one registered provider."""
        return list(self._providers.keys())


# Global registry instance
_registry = SpeechProviderRegistry()


def get_speech_provider_registry() -> SpeechProviderRegistry:
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
