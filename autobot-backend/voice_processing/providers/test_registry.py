# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Speech Provider Registry

Tests provider registration, routing, and language detection.
Part of Issue MVA-2185.
"""

import sys
from pathlib import Path

# Add autobot-backend to path for imports
backend_path = Path(__file__).parent.parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

# Import directly from providers submodule to avoid voice_processing/__init__.py
from voice_processing.providers import (
    ProviderRegistry,
    SpeechProvider,
    TranscriptSegment,
    get_speech_provider_registry,
    get_speech_provider,
)
from voice_processing.providers.generic_provider import GenericProvider
from voice_processing.providers.lv.late_provider import LateProvider
from voice_processing.providers.lv.tilde_provider import TildeProvider


class MockProvider(SpeechProvider):
    """Mock provider for testing."""

    def __init__(self, name: str, languages: list):
        self._name = name
        self._languages = languages

    async def transcribe(self, audio_path: str, language=None):
        return [
            TranscriptSegment(
                text=f"Mock transcription from {self._name}",
                start_time=0.0,
                end_time=1.0,
                confidence=0.95,
                language=language,
            )
        ]

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def supported_languages(self) -> list:
        return self._languages


class TestProviderRegistry:
    """Test provider registry functionality."""

    def test_register_and_get_provider(self):
        """Test basic provider registration and retrieval."""
        registry = ProviderRegistry()
        provider = MockProvider("TestProvider", ["en"])

        registry.register("en", provider, priority=10)

        retrieved = registry.get_provider("en")
        assert retrieved is not None
        assert retrieved.provider_name == "TestProvider"

    def test_priority_ordering(self):
        """Test that higher priority providers are returned first."""
        registry = ProviderRegistry()

        low_priority = MockProvider("LowPriority", ["en"])
        high_priority = MockProvider("HighPriority", ["en"])

        registry.register("en", low_priority, priority=5)
        registry.register("en", high_priority, priority=10)

        retrieved = registry.get_provider("en")
        assert retrieved.provider_name == "HighPriority"

    def test_get_all_providers(self):
        """Test getting all providers for a language."""
        registry = ProviderRegistry()

        provider1 = MockProvider("Provider1", ["en"])
        provider2 = MockProvider("Provider2", ["en"])
        provider3 = MockProvider("Provider3", ["en"])

        registry.register("en", provider1, priority=10)
        registry.register("en", provider2, priority=5)
        registry.register("en", provider3, priority=15)

        all_providers = registry.get_all_providers("en")
        assert len(all_providers) == 3

        # Should be ordered by priority (highest first)
        assert all_providers[0].provider_name == "Provider3"  # priority 15
        assert all_providers[1].provider_name == "Provider1"  # priority 10
        assert all_providers[2].provider_name == "Provider2"  # priority 5

    def test_no_provider_for_language(self):
        """Test behavior when no provider exists for a language."""
        registry = ProviderRegistry()

        provider = MockProvider("TestProvider", ["en"])
        registry.register("en", provider)

        # Try to get provider for unsupported language
        retrieved = registry.get_provider("fr")
        assert retrieved is None

    def test_multiple_languages_same_provider(self):
        """Test registering same provider for multiple languages."""
        registry = ProviderRegistry()
        provider = MockProvider("MultiLang", ["en", "de", "fr"])

        registry.register("en", provider)
        registry.register("de", provider)
        registry.register("fr", provider)

        assert registry.get_provider("en").provider_name == "MultiLang"
        assert registry.get_provider("de").provider_name == "MultiLang"
        assert registry.get_provider("fr").provider_name == "MultiLang"


class TestLatvianProviderRouting:
    """Test Latvian provider routing (LATE > Tilde > Generic)."""

    def test_latvian_routing_priority(self):
        """Test that 'lv' routes to LATE first, then Tilde, then Generic."""
        registry = ProviderRegistry()

        # Register in reverse order to test priority sorting
        generic = MockProvider("Generic", ["lv"])
        tilde = MockProvider("Tilde", ["lv"])
        late = MockProvider("LATE", ["lv"])

        registry.register("lv", generic, priority=-10)
        registry.register("lv", tilde, priority=5)
        registry.register("lv", late, priority=10)

        # Highest priority should be returned
        provider = registry.get_provider("lv")
        assert provider.provider_name == "LATE"

        # Get all to verify fallback chain
        all_providers = registry.get_all_providers("lv")
        assert len(all_providers) == 3
        assert all_providers[0].provider_name == "LATE"
        assert all_providers[1].provider_name == "Tilde"
        assert all_providers[2].provider_name == "Generic"

    def test_lat_code_routing(self):
        """Test that 'lat' (ISO 639-2) also routes to Latvian providers."""
        registry = ProviderRegistry()

        late = MockProvider("LATE", ["lat"])
        registry.register("lat", late, priority=10)

        provider = registry.get_provider("lat")
        assert provider.provider_name == "LATE"


class TestGenericProviderRouting:
    """Test generic provider routing for non-Latvian languages."""

    def test_english_routing(self):
        """Test that 'en' routes to Generic provider."""
        registry = ProviderRegistry()
        generic = MockProvider("Generic", ["en"])
        registry.register("en", generic, priority=0)

        provider = registry.get_provider("en")
        assert provider.provider_name == "Generic"

    def test_multiple_language_support(self):
        """Test generic provider supports multiple languages."""
        registry = ProviderRegistry()
        generic = MockProvider("Generic", ["en", "de", "es", "fr"])

        for lang in ["en", "de", "es", "fr"]:
            registry.register(lang, generic, priority=0)

        for lang in ["en", "de", "es", "fr"]:
            provider = registry.get_provider(lang)
            assert provider.provider_name == "Generic"


class TestRealProviders:
    """Test real provider implementations."""

    def test_late_provider_initialization(self):
        """Test LATE provider initializes correctly."""
        provider = LateProvider()
        assert provider.provider_name == "LATE"
        assert "lv" in provider.supported_languages
        assert "lat" in provider.supported_languages

    def test_tilde_provider_initialization(self):
        """Test Tilde provider initializes correctly."""
        provider = TildeProvider()
        assert provider.provider_name == "Tilde"
        assert "lv" in provider.supported_languages
        assert "lat" in provider.supported_languages

    def test_generic_provider_initialization(self):
        """Test Generic provider initializes correctly."""
        provider = GenericProvider()
        assert provider.provider_name == "Generic (Google/Sphinx)"
        assert "en" in provider.supported_languages
        assert len(provider.supported_languages) > 1


class TestGlobalRegistry:
    """Test global registry singleton."""

    def test_get_speech_provider_registry_singleton(self):
        """Test that get_speech_provider_registry returns same instance."""
        registry1 = get_speech_provider_registry()
        registry2 = get_speech_provider_registry()
        assert registry1 is registry2

    def test_get_speech_provider_convenience(self):
        """Test convenience function get_speech_provider."""
        # This will return provider from the global registry
        # which should have providers registered via registry_init
        provider = get_speech_provider("lv")

        # After registry_init, we should have providers for 'lv'
        # Note: This test assumes registry_init has been imported
        assert provider is not None
