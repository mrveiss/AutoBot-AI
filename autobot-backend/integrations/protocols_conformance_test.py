# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Conformance tests for MessagingProtocol, TTSProtocol, and the CapabilityRegistry (#11524).

Tests:
1. ``MessagingProtocol`` runtime isinstance check for all registered adapters.
2. Method-signature verification (inspect.signature) for send_message / fetch_messages.
3. Registry: register / resolve / absent-capability returns empty list.
4. Functional smoke: send_message and fetch_messages with mocked HTTP (no live calls).
5. TTSClient structural conformance to TTSProtocol (static assertion via issubclass).
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from integrations.base import IntegrationConfig
from integrations.capability_registry import MESSAGING, TTS, CapabilityRegistry
from integrations.communication_integration import DiscordIntegration, SlackIntegration
from integrations.messaging_adapters import DiscordMessagingAdapter, SlackMessagingAdapter
from integrations.protocols import MessagingProtocol, TTSProtocol

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def slack_config() -> IntegrationConfig:
    return IntegrationConfig(name="slack", provider="slack", token="xoxb-test")


@pytest.fixture()
def discord_config() -> IntegrationConfig:
    return IntegrationConfig(name="discord", provider="discord", token="Bot test-token")


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
        assert isinstance(slack_adapter, MessagingProtocol), (
            "SlackMessagingAdapter must satisfy MessagingProtocol"
        )

    def test_discord_adapter_isinstance(self, discord_adapter):
        assert isinstance(discord_adapter, MessagingProtocol), (
            "DiscordMessagingAdapter must satisfy MessagingProtocol"
        )

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
        assert inspect.iscoroutinefunction(impl.send_message), (
            f"{impl_name}.send_message must be a coroutine function"
        )

    @pytest.mark.parametrize("impl_name", ["slack", "discord"])
    def test_fetch_messages_is_coroutine(self, impl_name, slack_adapter, discord_adapter):
        impl = slack_adapter if impl_name == "slack" else discord_adapter
        assert inspect.iscoroutinefunction(impl.fetch_messages), (
            f"{impl_name}.fetch_messages must be a coroutine function"
        )


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
    async def test_fetch_messages_returns_empty_list(self, discord_adapter):
        result = await discord_adapter.fetch_messages("CH456")
        assert result == []


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
