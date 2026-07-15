# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Conformance tests for MessagingProtocol, TTSProtocol, STTProtocol, and the CapabilityRegistry.

Tests:
1. ``MessagingProtocol`` runtime isinstance check for all registered adapters.
2. Method-signature verification (inspect.signature) for send_message / fetch_messages.
3. Registry: register / resolve / absent-capability returns empty list.
4. Functional smoke: send_message and fetch_messages with mocked HTTP (no live calls).
5. TTSClient structural conformance to TTSProtocol (static assertion via issubclass).
6. Discord fetch_messages (#11560): real normalised history against a mocked HTTP call.
7. STTProtocol adapter (#11559): isinstance check + registry registration.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integrations.base import IntegrationConfig
from integrations.capability_registry import MESSAGING, STT, TTS, CapabilityRegistry
from integrations.communication_integration import DiscordIntegration, SlackIntegration
from integrations.messaging_adapters import DiscordMessagingAdapter, SlackMessagingAdapter
from integrations.protocols import MessagingProtocol, STTProtocol, TTSProtocol
from integrations.stt_adapter import SpeechProviderSTTAdapter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def slack_config() -> IntegrationConfig:
    return IntegrationConfig(name="slack", provider="slack", token="xoxb-test")


@pytest.fixture()
def discord_config() -> IntegrationConfig:
    return IntegrationConfig(name="discord", provider="discord", token="test-token")


@pytest.fixture()
def slack_adapter(slack_config: IntegrationConfig) -> SlackMessagingAdapter:
    return SlackMessagingAdapter(SlackIntegration(slack_config))


@pytest.fixture()
def discord_adapter(discord_config: IntegrationConfig) -> DiscordMessagingAdapter:
    return DiscordMessagingAdapter(DiscordIntegration(discord_config))


@pytest.fixture(params=["slack", "discord"])
def adapter(request, slack_adapter, discord_adapter):
    """Parametrised fixture covering both registered MessagingProtocol adapters."""
    return slack_adapter if request.param == "slack" else discord_adapter


# ---------------------------------------------------------------------------
# 1. Runtime isinstance conformance
# ---------------------------------------------------------------------------


class TestMessagingProtocolConformance:
    def test_slack_adapter_isinstance(self, slack_adapter):
        assert isinstance(slack_adapter, MessagingProtocol), "SlackMessagingAdapter must satisfy MessagingProtocol"

    def test_discord_adapter_isinstance(self, discord_adapter):
        assert isinstance(discord_adapter, MessagingProtocol), "DiscordMessagingAdapter must satisfy MessagingProtocol"

    def test_plain_dict_is_not_messaging_protocol(self):
        assert not isinstance({}, MessagingProtocol)

    def test_object_without_methods_is_not_messaging_protocol(self):
        class Bare:
            pass

        assert not isinstance(Bare(), MessagingProtocol)


# ---------------------------------------------------------------------------
# 2. Method-signature verification
# ---------------------------------------------------------------------------


class TestMessagingProtocolSignatures:
    @pytest.mark.parametrize("impl_name", ["slack", "discord"])
    def test_send_message_signature(self, impl_name, slack_adapter, discord_adapter):
        impl = slack_adapter if impl_name == "slack" else discord_adapter
        sig = inspect.signature(impl.send_message)
        params = list(sig.parameters)
        assert "channel_id" in params, f"{impl_name}: send_message missing 'channel_id'"
        assert "text" in params, f"{impl_name}: send_message missing 'text'"

    @pytest.mark.parametrize("impl_name", ["slack", "discord"])
    def test_fetch_messages_signature(self, impl_name, slack_adapter, discord_adapter):
        impl = slack_adapter if impl_name == "slack" else discord_adapter
        sig = inspect.signature(impl.fetch_messages)
        params = list(sig.parameters)
        assert "channel_id" in params, f"{impl_name}: fetch_messages missing 'channel_id'"
        assert "limit" in params, f"{impl_name}: fetch_messages missing 'limit'"

    @pytest.mark.parametrize("impl_name", ["slack", "discord"])
    def test_send_message_is_coroutine(self, impl_name, slack_adapter, discord_adapter):
        impl = slack_adapter if impl_name == "slack" else discord_adapter
        assert inspect.iscoroutinefunction(impl.send_message), f"{impl_name}.send_message must be a coroutine function"

    @pytest.mark.parametrize("impl_name", ["slack", "discord"])
    def test_fetch_messages_is_coroutine(self, impl_name, slack_adapter, discord_adapter):
        impl = slack_adapter if impl_name == "slack" else discord_adapter
        assert inspect.iscoroutinefunction(
            impl.fetch_messages
        ), f"{impl_name}.fetch_messages must be a coroutine function"


# ---------------------------------------------------------------------------
# 3. CapabilityRegistry: register / resolve / absent returns []
# ---------------------------------------------------------------------------


class TestCapabilityRegistry:
    def test_resolve_absent_returns_empty_list(self):
        registry = CapabilityRegistry()
        assert registry.resolve("nonexistent") == []

    def test_register_and_resolve(self):
        registry = CapabilityRegistry()
        impl = MagicMock()
        registry.register(MESSAGING, impl)
        resolved = registry.resolve(MESSAGING)
        assert resolved == [impl]

    def test_resolve_preserves_registration_order(self):
        registry = CapabilityRegistry()
        impl_a, impl_b = MagicMock(), MagicMock()
        registry.register(MESSAGING, impl_a)
        registry.register(MESSAGING, impl_b)
        assert registry.resolve(MESSAGING) == [impl_a, impl_b]

    def test_capabilities_lists_registered_names(self):
        registry = CapabilityRegistry()
        registry.register(MESSAGING, MagicMock())
        registry.register(TTS, MagicMock())
        assert MESSAGING in registry.capabilities()
        assert TTS in registry.capabilities()

    def test_resolve_returns_independent_copy(self):
        registry = CapabilityRegistry()
        registry.register(MESSAGING, MagicMock())
        lst = registry.resolve(MESSAGING)
        lst.append(MagicMock())  # mutate the returned copy
        assert len(registry.resolve(MESSAGING)) == 1  # original unaffected

    def test_register_multiple_capabilities_independently(self):
        registry = CapabilityRegistry()
        m_impl = MagicMock()
        t_impl = MagicMock()
        registry.register(MESSAGING, m_impl)
        registry.register(TTS, t_impl)
        assert registry.resolve(MESSAGING) == [m_impl]
        assert registry.resolve(TTS) == [t_impl]


# ---------------------------------------------------------------------------
# 4. Functional smoke tests (mocked HTTP)
# ---------------------------------------------------------------------------


class TestSlackAdapterFunctional:
    @pytest.mark.asyncio
    async def test_send_message_delegates_to_execute_action(self, slack_adapter):
        slack_adapter._integration.execute_action = AsyncMock(return_value={"ok": True})
        result = await slack_adapter.send_message("C123", "hello")
        slack_adapter._integration.execute_action.assert_awaited_once_with(
            "send_message", {"channel": "C123", "text": "hello"}
        )
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_fetch_messages_returns_list(self, slack_adapter):
        slack_adapter._integration.execute_action = AsyncMock(
            return_value={"messages": [{"text": "hi"}, {"text": "there"}]}
        )
        result = await slack_adapter.fetch_messages("C123", limit=50)
        assert result == [{"text": "hi"}, {"text": "there"}]
        slack_adapter._integration.execute_action.assert_awaited_once_with(
            "get_channel_history", {"channel": "C123", "limit": 50}
        )

    @pytest.mark.asyncio
    async def test_fetch_messages_empty_on_bad_payload(self, slack_adapter):
        slack_adapter._integration.execute_action = AsyncMock(return_value={"ok": False})
        result = await slack_adapter.fetch_messages("C123")
        assert result == []

    @pytest.mark.asyncio
    async def test_send_message_with_kwargs(self, slack_adapter):
        slack_adapter._integration.execute_action = AsyncMock(return_value={"ok": True})
        await slack_adapter.send_message("C999", "msg", blocks=[{"type": "section"}])
        call_params = slack_adapter._integration.execute_action.call_args[0][1]
        assert call_params["blocks"] == [{"type": "section"}]


class TestDiscordAdapterFunctional:
    @pytest.mark.asyncio
    async def test_send_message_translates_text_to_content(self, discord_adapter):
        discord_adapter._integration.execute_action = AsyncMock(return_value={"id": "msg1"})
        result = await discord_adapter.send_message("CH456", "world")
        discord_adapter._integration.execute_action.assert_awaited_once_with(
            "send_message", {"channel_id": "CH456", "content": "world"}
        )
        assert result == {"id": "msg1"}

    @pytest.mark.asyncio
    async def test_fetch_messages_returns_normalised_history(self, discord_adapter):
        """#11560: fetch_messages routes through get_channel_history and normalises (#11560)."""
        raw_messages = [
            {"id": "1", "content": "hello", "author": {"username": "alice"}},
            {"id": "2", "content": "world", "author": {"username": "bob"}},
        ]
        discord_adapter._integration.execute_action = AsyncMock(
            return_value={"messages": raw_messages, "channel_id": "CH456"}
        )
        result = await discord_adapter.fetch_messages("CH456", limit=2)
        discord_adapter._integration.execute_action.assert_awaited_once_with(
            "get_channel_history", {"channel_id": "CH456", "limit": 2}
        )
        assert result == raw_messages

    @pytest.mark.asyncio
    async def test_fetch_messages_returns_empty_on_bad_payload(self, discord_adapter):
        """fetch_messages returns [] when response has no 'messages' key."""
        discord_adapter._integration.execute_action = AsyncMock(return_value={"error": "not_found"})
        result = await discord_adapter.fetch_messages("CH456")
        assert result == []

    @pytest.mark.asyncio
    async def test_discord_get_channel_history_action_mocked_http(self, discord_adapter):
        """#11560: integration-level: get_channel_history action builds correct URL / auth."""
        integration = discord_adapter._integration
        raw_body = [{"id": "3", "content": "hi"}]

        # Patch _make_discord_request so no live HTTP occurs.
        integration._make_discord_request = AsyncMock(return_value={"status_code": 200, "body": raw_body})
        result = await integration.execute_action("get_channel_history", {"channel_id": "789", "limit": 5})

        # Verify the method was called with correct URL fragment and auth header.
        call_kwargs = integration._make_discord_request.call_args
        assert "channels/789/messages" in call_kwargs[0][1]  # url positional arg
        assert call_kwargs[0][2]["Authorization"] == "Bot test-token"
        assert result == {"messages": raw_body, "channel_id": "789"}


# ---------------------------------------------------------------------------
# 5. TTSProtocol static conformance
# ---------------------------------------------------------------------------


class TestTTSProtocolConformance:
    def test_tts_client_satisfies_tts_protocol_structurally(self):
        """TTSClient must be structurally compatible with TTSProtocol.

        issubclass with a runtime_checkable Protocol verifies only *method
        presence*, not signatures.  The import is lazy so the test is skipped
        gracefully when the TTS worker dependencies are unavailable.
        """
        try:
            from services.tts_client import TTSClient
        except ImportError:
            pytest.skip("services.tts_client not importable in this environment")

        assert issubclass(TTSClient, TTSProtocol), "TTSClient must satisfy TTSProtocol"

    def test_tts_protocol_instance_check(self):
        """A concrete class with the required methods is isinstance-compatible."""

        class MockTTS:
            async def synthesize(self, text: str, voice_id: str = "", language: str = "") -> bytes:
                return b""

            async def is_available(self) -> bool:
                return True

        assert isinstance(MockTTS(), TTSProtocol)

    def test_incomplete_tts_fails_isinstance(self):
        """A class missing ``is_available`` does not satisfy TTSProtocol."""

        class IncompleteTTS:
            async def synthesize(self, text: str, voice_id: str = "", language: str = "") -> bytes:
                return b""

        assert not isinstance(IncompleteTTS(), TTSProtocol)


# ---------------------------------------------------------------------------
# 6. STTProtocol conformance and adapter (#11559)
# ---------------------------------------------------------------------------


class _FakeSegment:
    """Minimal stand-in for ``voice_processing.providers.TranscriptSegment``."""

    def __init__(self, text, start_time, end_time, confidence):
        self.text = text
        self.start_time = start_time
        self.end_time = end_time
        self.confidence = confidence


class TestSTTProtocolConformance:
    def test_adapter_satisfies_stt_protocol(self):
        """SpeechProviderSTTAdapter must satisfy STTProtocol at runtime."""
        mock_provider = MagicMock()
        adapter = SpeechProviderSTTAdapter(mock_provider)
        assert isinstance(adapter, STTProtocol), "SpeechProviderSTTAdapter must satisfy STTProtocol"

    def test_concrete_class_satisfies_stt_protocol(self):
        """Any class with ``transcribe`` is isinstance-compatible with STTProtocol."""

        class MockSTT:
            async def transcribe(self, audio_path: str, language=None) -> list:
                return []

        assert isinstance(MockSTT(), STTProtocol)

    def test_object_without_transcribe_fails_isinstance(self):
        """A class lacking ``transcribe`` does not satisfy STTProtocol."""

        class NotSTT:
            pass

        assert not isinstance(NotSTT(), STTProtocol)

    @pytest.mark.asyncio
    async def test_adapter_transcribe_normalises_segments(self):
        """Adapter converts TranscriptSegment objects to plain dicts."""
        segments = [
            _FakeSegment("hello world", 0.0, 1.5, 0.95),
            _FakeSegment("goodbye", 1.5, 2.8, 0.88),
        ]
        mock_provider = MagicMock()
        mock_provider.transcribe = AsyncMock(return_value=segments)
        adapter = SpeechProviderSTTAdapter(mock_provider)

        result = await adapter.transcribe("/tmp/audio.wav", language="en")

        assert result == [
            {"text": "hello world", "start_time": 0.0, "end_time": 1.5, "confidence": 0.95},
            {"text": "goodbye", "start_time": 1.5, "end_time": 2.8, "confidence": 0.88},
        ]
        mock_provider.transcribe.assert_awaited_once_with("/tmp/audio.wav", language="en")

    @pytest.mark.asyncio
    async def test_adapter_returns_empty_on_provider_error(self):
        """Adapter swallows provider exceptions and returns empty list."""
        mock_provider = MagicMock()
        mock_provider.transcribe = AsyncMock(side_effect=RuntimeError("provider down"))
        adapter = SpeechProviderSTTAdapter(mock_provider)

        result = await adapter.transcribe("/tmp/audio.wav")
        assert result == []

    def test_stt_registered_in_capability_registry(self):
        """SpeechProviderSTTAdapter is resolvable via CapabilityRegistry (#11559)."""
        registry = CapabilityRegistry()
        mock_provider = MagicMock()
        mock_provider.provider_name = "mock-stt"
        adapter = SpeechProviderSTTAdapter(mock_provider)
        registry.register(STT, adapter)

        resolved = registry.resolve(STT)
        assert len(resolved) == 1
        assert isinstance(resolved[0], STTProtocol)
        assert isinstance(resolved[0], SpeechProviderSTTAdapter)


# ---------------------------------------------------------------------------
# 7. Multi-language STT registration (#11617)
# ---------------------------------------------------------------------------


class _FakeSpeechRegistry:
    """Minimal stand-in for ``voice_processing.providers.ProviderRegistry``.

    Mirrors the real registry's ``_providers`` dict structure
    (``{lang: [(provider, priority), ...]}``) and ``get_provider`` API.
    """

    def __init__(self, providers_by_lang: dict) -> None:
        # providers_by_lang: {lang: SpeechProvider}
        # Build the (provider, priority) tuple structure the real registry uses.
        self._providers = {lang: [(provider, 0)] for lang, provider in providers_by_lang.items()}

    def get_provider(self, language: str):
        entries = self._providers.get(language)
        if not entries:
            return None
        return entries[0][0]

    def languages(self):
        """Match the real ProviderRegistry.languages() public accessor (#11617)."""
        return list(self._providers.keys())


def _make_mock_provider(name: str):
    """Return a MagicMock SpeechProvider with provider_name set."""
    provider = MagicMock()
    provider.provider_name = name
    return provider


class TestSTTMultiLanguageRegistration:
    """#11617 — every language in the speech registry must get an STT adapter."""

    def _run_register(self, fake_speech_registry):
        """Run ``_register_stt_language`` per language with a fake registry injected."""
        from integrations.capability_registry import _register_stt_language

        registry = CapabilityRegistry()
        for lang in fake_speech_registry.languages():
            _register_stt_language(registry, fake_speech_registry, lang, SpeechProviderSTTAdapter)
        return registry

    def test_register_stt_if_available_enumerates_via_languages(self):
        """End-to-end: the production entry point enumerates via .languages() (#11617).

        Drives the real ``_register_stt_if_available`` with the fake speech
        registry injected, so the public-accessor enumeration path is covered —
        not just the per-language helper.
        """
        import integrations.capability_registry as cr
        from voice_processing import providers as vp

        fake_reg = _FakeSpeechRegistry(
            {"en": _make_mock_provider("whisper-en"), "lv": _make_mock_provider("whisper-lv")}
        )
        registry = CapabilityRegistry()
        with patch.object(vp, "get_speech_provider_registry", return_value=fake_reg):
            cr._register_stt_if_available(registry)

        resolved = registry.resolve(STT)
        assert len(resolved) == 2
        assert all(isinstance(a, STTProtocol) for a in resolved)

    def test_single_language_registers_one_adapter(self):
        """A registry with one language produces exactly one STT adapter."""
        fake_reg = _FakeSpeechRegistry({"en": _make_mock_provider("whisper-en")})
        registry = self._run_register(fake_reg)

        resolved = registry.resolve(STT)
        assert len(resolved) == 1
        assert isinstance(resolved[0], STTProtocol)
        assert isinstance(resolved[0], SpeechProviderSTTAdapter)

    def test_multi_language_registers_one_adapter_per_language(self):
        """Each language in the speech registry gets its own STT adapter (#11617)."""
        fake_reg = _FakeSpeechRegistry(
            {
                "en": _make_mock_provider("whisper-en"),
                "lv": _make_mock_provider("whisper-lv"),
                "de": _make_mock_provider("whisper-de"),
            }
        )
        registry = self._run_register(fake_reg)

        resolved = registry.resolve(STT)
        assert len(resolved) == 3
        for adapter in resolved:
            assert isinstance(adapter, STTProtocol)
            assert isinstance(adapter, SpeechProviderSTTAdapter)

    def test_en_provider_still_resolvable_alongside_others(self):
        """Existing 'en' behaviour is preserved when other languages are present."""
        en_provider = _make_mock_provider("whisper-en")
        fake_reg = _FakeSpeechRegistry({"en": en_provider, "fr": _make_mock_provider("whisper-fr")})
        registry = self._run_register(fake_reg)

        resolved = registry.resolve(STT)
        assert len(resolved) == 2
        # The first registered language is 'en'; its adapter wraps en_provider.
        assert resolved[0]._provider is en_provider

    def test_empty_speech_registry_registers_no_adapters(self):
        """An empty speech registry results in no STT capability entries."""
        fake_reg = _FakeSpeechRegistry({})
        registry = self._run_register(fake_reg)

        assert registry.resolve(STT) == []

    def test_language_with_no_provider_is_skipped(self):
        """If get_provider returns None for a language, that language is skipped."""
        from integrations.capability_registry import _register_stt_language

        # Build a registry that has a language key but the provider returns None.
        fake_reg = _FakeSpeechRegistry({"en": _make_mock_provider("whisper-en")})
        # Patch get_provider to return None for 'en'.
        fake_reg.get_provider = lambda lang: None

        registry = CapabilityRegistry()
        _register_stt_language(registry, fake_reg, "en", SpeechProviderSTTAdapter)

        assert registry.resolve(STT) == []

    def test_failing_language_does_not_block_others(self):
        """A per-language registration failure is caught; other languages still register."""
        from integrations.capability_registry import _register_stt_language

        en_provider = _make_mock_provider("whisper-en")
        fr_provider = _make_mock_provider("whisper-fr")

        # Simulate 'lv' provider raising on construction.
        def bad_adapter(provider):
            if provider.provider_name == "whisper-lv":
                raise RuntimeError("deps missing")
            return SpeechProviderSTTAdapter(provider)

        fake_reg = _FakeSpeechRegistry({"en": en_provider, "lv": _make_mock_provider("whisper-lv"), "fr": fr_provider})
        registry = CapabilityRegistry()
        for lang in ["en", "lv", "fr"]:
            _register_stt_language(registry, fake_reg, lang, bad_adapter)

        resolved = registry.resolve(STT)
        # 'lv' failed — only 'en' and 'fr' should be registered.
        assert len(resolved) == 2
        provider_names = {a._provider.provider_name for a in resolved}
        assert provider_names == {"whisper-en", "whisper-fr"}
