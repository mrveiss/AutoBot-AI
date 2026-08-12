# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Comprehensive tests for Unified Multi-Platform Message Gateway

Tests verify:
- GatewayManager accepts messages from 9+ platforms
- Platform adapters with request/response normalization
- Rate limiting per platform
- Message queue with async processing
- Message routing correct for 9+ platforms
- Performance: <50ms per message
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from services.gateway import (
    DiscordAdapter,
    GatewayManager,
    GatewayMessage,
    NormalizedResponse,
    SlackAdapter,
    TeamsAdapter,
    WebAdapter,
    WhatsAppAdapter,
)
from services.gateway.message_queue import MessageQueue, gateway_rate_limiter


class TestSlackAdapter:
    """Test Slack platform adapter."""

    @pytest.fixture
    def adapter(self):
        return SlackAdapter()

    @pytest.mark.asyncio
    async def test_normalize_slack_message(self, adapter):
        """Test normalizing Slack message to unified schema."""
        raw = {
            "user_id": "U123",
            "channel_id": "C456",
            "text": "Hello from Slack",
            "timestamp": "1234567890.123456",
        }

        unified = await adapter.normalize_message(raw)

        assert isinstance(unified, GatewayMessage)
        assert unified.user_id == "U123"
        assert unified.platform == "slack"
        assert unified.channel_id == "C456"
        assert unified.message == "Hello from Slack"
        assert unified.metadata["is_thread_reply"] is False

    @pytest.mark.asyncio
    async def test_denormalize_slack_response(self, adapter):
        """Test converting unified response back to Slack format."""
        response = NormalizedResponse(
            platform="slack",
            channel_id="C456",
            user_id="U123",
            content="Hello back",
            response_type="message",
            metadata={},
        )

        slack_response = await adapter.denormalize_response(response)

        assert slack_response["channel"] == "C456"
        assert slack_response["text"] == "Hello back"
        assert slack_response["user"] == "U123"

    def test_slack_rate_limit(self, adapter):
        """Test Slack rate limit configuration."""
        limits = adapter.get_rate_limit()
        assert limits["requests_per_second"] == 1
        assert limits["burst_size"] == 10

    @pytest.mark.asyncio
    async def test_slack_thread_reply(self, adapter):
        """Test Slack thread reply normalization."""
        raw = {
            "user_id": "U123",
            "channel_id": "C456",
            "text": "Thread reply",
            "timestamp": "1234567890.123456",
            "thread_ts": "1234567890.000000",
        }

        unified = await adapter.normalize_message(raw)
        assert unified.metadata["is_thread_reply"] is True
        assert unified.metadata["thread_ts"] == "1234567890.000000"


class TestDiscordAdapter:
    """Test Discord platform adapter."""

    @pytest.fixture
    def adapter(self):
        return DiscordAdapter()

    @pytest.mark.asyncio
    async def test_normalize_discord_message(self, adapter):
        """Test normalizing Discord message to unified schema."""
        raw = {
            "author": {"id": "user123"},
            "channel_id": "chan456",
            "content": "Hello from Discord",
            "timestamp": "1234567890",
            "id": "msg789",
        }

        unified = await adapter.normalize_message(raw)

        assert unified.user_id == "user123"
        assert unified.platform == "discord"
        assert unified.channel_id == "chan456"
        assert unified.message == "Hello from Discord"
        assert unified.metadata["message_id"] == "msg789"

    @pytest.mark.asyncio
    async def test_denormalize_discord_response(self, adapter):
        """Test converting unified response back to Discord format."""
        response = NormalizedResponse(
            platform="discord",
            channel_id="chan456",
            user_id="user123",
            content="Hello back",
            response_type="message",
            metadata={},
        )

        discord_response = await adapter.denormalize_response(response)

        assert discord_response["channel_id"] == "chan456"
        assert discord_response["content"] == "Hello back"

    def test_discord_rate_limit(self, adapter):
        """Test Discord rate limit configuration."""
        limits = adapter.get_rate_limit()
        assert limits["requests_per_second"] == 10
        assert limits["burst_size"] == 50


class TestWhatsAppAdapter:
    """Test WhatsApp platform adapter."""

    @pytest.fixture
    def adapter(self):
        return WhatsAppAdapter()

    @pytest.mark.asyncio
    async def test_normalize_whatsapp_message(self, adapter):
        """Test normalizing WhatsApp message."""
        raw = {
            "from": "1234567890",
            "chat_id": "groupchat",
            "body": "Hello from WhatsApp",
            "timestamp": "1234567890",
            "id": "msg123",
        }

        unified = await adapter.normalize_message(raw)

        assert unified.user_id == "1234567890"
        assert unified.platform == "whatsapp"
        assert unified.channel_id == "groupchat"
        assert unified.message == "Hello from WhatsApp"

    def test_whatsapp_rate_limit(self, adapter):
        """Test WhatsApp rate limit configuration."""
        limits = adapter.get_rate_limit()
        assert limits["requests_per_second"] == 80
        assert limits["burst_size"] == 100


class TestTeamsAdapter:
    """Test Microsoft Teams adapter."""

    @pytest.fixture
    def adapter(self):
        return TeamsAdapter()

    @pytest.mark.asyncio
    async def test_normalize_teams_message(self, adapter):
        """Test normalizing Teams message."""
        raw = {
            "from": {"id": "user123"},
            "channelData": {"channel": {"id": "chan456"}},
            "text": "Hello from Teams",
            "timestamp": "1234567890",
            "id": "msg789",
        }

        unified = await adapter.normalize_message(raw)

        assert unified.user_id == "user123"
        assert unified.platform == "teams"
        assert unified.channel_id == "chan456"
        assert unified.message == "Hello from Teams"

    def test_teams_rate_limit(self, adapter):
        """Test Teams rate limit configuration."""
        limits = adapter.get_rate_limit()
        assert limits["requests_per_second"] == 50
        assert limits["burst_size"] == 100


class TestWebAdapter:
    """Test Web platform adapter."""

    @pytest.fixture
    def adapter(self):
        return WebAdapter()

    @pytest.mark.asyncio
    async def test_normalize_web_message(self, adapter):
        """Test normalizing web message."""
        raw = {
            "user_id": "webuser",
            "channel_id": "main",
            "message": "Hello from web",
            "timestamp": "1234567890",
            "session_id": "sess123",
        }

        unified = await adapter.normalize_message(raw)

        assert unified.user_id == "webuser"
        assert unified.platform == "web"
        assert unified.channel_id == "main"
        assert unified.message == "Hello from web"

    def test_web_rate_limit(self, adapter):
        """Test Web rate limit configuration."""
        limits = adapter.get_rate_limit()
        assert limits["requests_per_second"] == 100
        assert limits["burst_size"] == 200


class TestGatewayManager:
    """Test main gateway manager."""

    @pytest.fixture
    def gateway(self):
        return GatewayManager()

    def test_gateway_initialization(self, gateway):
        """Test gateway initializes with all adapters."""
        adapters = gateway.get_supported_platforms()
        assert "web" in adapters
        assert "slack" in adapters
        assert "discord" in adapters
        assert "whatsapp" in adapters
        assert "teams" in adapters
        assert "telegram" in adapters
        assert "signal" in adapters
        assert "matrix" in adapters
        assert "imessage" in adapters
        assert len(adapters) == 9

    @pytest.mark.asyncio
    async def test_normalize_web_message(self, gateway):
        """Test normalizing web message through gateway."""
        raw = {
            "platform": "web",
            "user_id": "webuser",
            "channel_id": "main",
            "message": "Test message",
            "timestamp": time.time(),
            "message_id": "msg-web-1",
        }

        start = time.time()
        unified = await gateway.normalize_message(raw)
        elapsed_ms = (time.time() - start) * 1000

        assert unified.platform == "web"
        assert unified.user_id == "webuser"
        assert elapsed_ms < 50  # Performance requirement

    @pytest.mark.asyncio
    async def test_normalize_slack_message(self, gateway):
        """Test normalizing Slack message through gateway."""
        raw = {
            "platform": "slack",
            "user_id": "U123",
            "channel_id": "C456",
            "text": "Hello from Slack",
            "timestamp": time.time(),
            "message": "Hello from Slack",  # Slack adapter needs both for validation
        }

        start = time.time()
        unified = await gateway.normalize_message(raw)
        elapsed_ms = (time.time() - start) * 1000

        assert unified.platform == "slack"
        assert unified.user_id == "U123"
        assert elapsed_ms < 50

    @pytest.mark.asyncio
    async def test_normalize_discord_message(self, gateway):
        """Test normalizing Discord message through gateway."""
        raw = {
            "platform": "discord",
            "author": {"id": "user123"},
            "channel_id": "chan456",
            "content": "Hello from Discord",
            "timestamp": time.time(),
            "id": "msg789",
        }

        start = time.time()
        unified = await gateway.normalize_message(raw)
        elapsed_ms = (time.time() - start) * 1000

        assert unified.platform == "discord"
        assert unified.user_id == "user123"
        assert elapsed_ms < 50

    @pytest.mark.asyncio
    async def test_normalize_whatsapp_message(self, gateway):
        """Test normalizing WhatsApp message through gateway."""
        raw = {
            "platform": "whatsapp",
            "from": "1234567890",
            "chat_id": "groupchat",
            "body": "Hello from WhatsApp",
            "timestamp": time.time(),
            "id": "msg123",
        }

        start = time.time()
        unified = await gateway.normalize_message(raw)
        elapsed_ms = (time.time() - start) * 1000

        assert unified.platform == "whatsapp"
        assert unified.user_id == "1234567890"
        assert elapsed_ms < 50

    @pytest.mark.asyncio
    async def test_normalize_teams_message(self, gateway):
        """Test normalizing Teams message through gateway."""
        raw = {
            "platform": "teams",
            "from": {"id": "user123"},
            "channelData": {"channel": {"id": "chan456"}},
            "text": "Hello from Teams",
            "timestamp": time.time(),
            "id": "msg789",
        }

        start = time.time()
        unified = await gateway.normalize_message(raw)
        elapsed_ms = (time.time() - start) * 1000

        assert unified.platform == "teams"
        assert unified.user_id == "user123"
        assert elapsed_ms < 50

    @pytest.mark.asyncio
    async def test_denormalize_response(self, gateway):
        """Test denormalizing response."""
        response = NormalizedResponse(
            platform="slack",
            channel_id="C456",
            user_id="U123",
            content="Response",
            response_type="message",
            metadata={},
        )

        platform_response = await gateway.denormalize_response(response)
        assert platform_response["channel"] == "C456"

    @pytest.mark.asyncio
    async def test_missing_platform_field(self, gateway):
        """Test error when platform field is missing."""
        raw = {
            "user_id": "U123",
            "channel_id": "C456",
            "text": "Test",
        }

        with pytest.raises(ValueError, match="missing required 'platform'"):
            await gateway.normalize_message(raw)

    @pytest.mark.asyncio
    async def test_unsupported_platform(self, gateway):
        """Test error for unsupported platform."""
        raw = {
            "platform": "unknown_platform_xyz",
            "user_id": "U123",
            "channel_id": "C456",
            "message": "Test",
        }

        with pytest.raises(ValueError, match="Unsupported platform"):
            await gateway.normalize_message(raw)

    @pytest.mark.asyncio
    async def test_register_response_handler(self, gateway):
        """Test registering response handler for platform."""
        handler = AsyncMock()
        gateway.register_response_handler("slack", handler)

        assert "slack" in gateway.response_handlers

    @pytest.mark.asyncio
    async def test_route_message(self, gateway):
        """Test routing message through agent."""
        unified = GatewayMessage(
            user_id="U123",
            platform="slack",
            channel_id="C456",
            message="Test",
            timestamp=time.time(),
            metadata={},
        )

        agent_handler = AsyncMock(return_value={"response": "Response text", "type": "message"})

        handler = AsyncMock()
        gateway.register_response_handler("slack", handler)

        await gateway.route_message(unified, agent_handler)

        agent_handler.assert_called_once()
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueue_message(self, gateway):
        """Test enqueueing message."""
        raw = {
            "platform": "web",
            "user_id": "user1",
            "channel_id": "main",
            "message": "Test",
        }

        await gateway.enqueue_message(raw)
        # Queue should accept without raising

    @pytest.mark.asyncio
    async def test_get_adapter(self, gateway):
        """Test getting adapter for platform."""
        slack_adapter = gateway.get_adapter("slack")
        assert slack_adapter is not None
        assert isinstance(slack_adapter, SlackAdapter)

    def test_get_supported_platforms(self, gateway):
        """Test getting list of supported platforms."""
        platforms = gateway.get_supported_platforms()
        assert len(platforms) == 9
        assert set(platforms) == {
            "web",
            "slack",
            "discord",
            "whatsapp",
            "teams",
            "telegram",
            "signal",
            "matrix",
            "imessage",
        }


class TestPlatformRateLimitWiring:
    """MessageQueue delegates per-platform rate limiting to the shared
    RateLimiter's token-bucket mode (``acquire_token``) — migrated off the
    retired local token-bucket dataclass (#12646). The token-bucket
    algorithm itself is covered by autobot_shared/rate_limiter_test.py;
    these tests pin the register_platform -> acquire_token wiring."""

    def test_register_platform_stores_limits(self):
        queue = MessageQueue()
        queue.register_platform("slack", 1, 5)
        assert queue.platform_limits["slack"] == (1, 5)

    @pytest.mark.asyncio
    async def test_worker_acquires_token_with_registered_limits(self):
        """The worker must call acquire_token with this platform's exact
        (requests_per_second, burst_size) before dispatching the handler."""
        queue = MessageQueue()
        queue.register_platform("wiring-test-platform", 50, 10)

        processed = []

        async def handler(msg):
            processed.append(msg)

        await queue.enqueue({"platform": "wiring-test-platform", "data": "value"})

        with patch.object(gateway_rate_limiter, "acquire_token", AsyncMock()) as mock_acquire:
            task = asyncio.create_task(queue.process_queue(handler, workers=1))
            await asyncio.sleep(0.2)
            queue.processing = False
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except asyncio.TimeoutError:
                pass

        assert processed == [{"platform": "wiring-test-platform", "data": "value"}]
        mock_acquire.assert_called_once_with("wiring-test-platform", requests_per_second=50, burst_size=10)


class TestMessageQueue:
    """Test message queue integration."""

    @pytest.mark.asyncio
    async def test_message_queue_processing(self):
        """Test message queue processes messages."""
        queue = MessageQueue()
        queue.register_platform("test", 100, 200)

        processed = []

        async def handler(msg):
            processed.append(msg)

        # Enqueue a message
        await queue.enqueue({"platform": "test", "data": "value"})

        # Process with timeout
        process_task = asyncio.create_task(queue.process_queue(handler, workers=1))
        await asyncio.sleep(0.2)
        queue.processing = False

        try:
            await asyncio.wait_for(process_task, timeout=2.0)
        except asyncio.TimeoutError:
            pass

        await queue.shutdown()


class TestGatewayIntegration:
    """Integration tests for gateway."""

    @pytest.mark.asyncio
    async def test_multi_platform_routing(self):
        """Test routing messages from multiple platforms."""
        gateway = GatewayManager()

        messages = [
            {
                "platform": "web",
                "user_id": "web1",
                "channel_id": "main",
                "message": "Web message",
                "timestamp": time.time(),
                "message_id": "msg-web-multi",
            },
            {
                "platform": "slack",
                "user_id": "U123",
                "channel_id": "C456",
                "text": "Slack message",
                "timestamp": time.time(),
            },
            {
                "platform": "discord",
                "author": {"id": "user123"},
                "channel_id": "chan456",
                "content": "Discord message",
                "timestamp": time.time(),
                "id": "msg789",
            },
        ]

        results = []
        for raw in messages:
            unified = await gateway.normalize_message(raw)
            results.append(unified)

        assert len(results) == 3
        assert results[0].platform == "web"
        assert results[1].platform == "slack"
        assert results[2].platform == "discord"


class TestIngestGovernanceWiring:
    """#14028: bot-self filter, dedup, and recursion guard at the shared
    ``GatewayManager.normalize_message`` seam — the seam every registered
    platform adapter goes through, so this covers all 9 without per-adapter
    tests (a newly registered adapter inherits it for free)."""

    @pytest.fixture(autouse=True)
    def _fake_redis(self, monkeypatch):
        """A real-enough async Redis stand-in so dedup exercises its happy path
        instead of always fail-opening (conftest.py stubs the real client to
        return None for every backend unit test)."""
        from services.gateway import ingest_governor as governor_module

        store: dict = {}

        class _FakeAsyncRedis:
            async def set(self, key, value, nx=False, ex=None):
                if nx and key in store:
                    return None
                store[key] = value
                return True

        async def _get(*_a, **_k):
            return _FakeAsyncRedis()

        monkeypatch.setattr(governor_module, "get_async_redis_client", _get)
        yield store

    @pytest.mark.asyncio
    async def test_governance_stage_actually_runs_on_the_live_seam(self, monkeypatch):
        """Not a source-text substring check: wraps the real ``evaluate`` with a
        spy, drives ``normalize_message`` for real, and asserts the stage was
        actually invoked with this message's identity. Fails if a future
        change stops calling it, even if normalize_message otherwise still
        returns a message (#14028)."""
        from services.gateway import ingest_governor as governor_module

        real_evaluate = governor_module.ingest_governor.evaluate
        calls = []

        async def _spy(**kwargs):
            calls.append(kwargs)
            return await real_evaluate(**kwargs)

        monkeypatch.setattr(governor_module.ingest_governor, "evaluate", _spy)

        gateway = GatewayManager()
        raw = {
            "platform": "discord",
            "author": {"id": "user1"},
            "channel_id": "chanZ",
            "content": "hello",
            "timestamp": time.time(),
            "id": "wire-check-1",
        }
        unified = await gateway.normalize_message(raw)

        assert unified is not None
        assert len(calls) == 1
        assert calls[0]["platform"] == "discord"
        assert calls[0]["message_id"] == "wire-check-1"
        assert calls[0]["author_id"] == "user1"

    @pytest.mark.asyncio
    async def test_bot_self_authored_message_dropped_before_routing(self, monkeypatch):
        """A synthetic echo of the bot's own outbound message never reaches
        the caller as a routable message."""
        monkeypatch.setenv("AUTOBOT_GATEWAY_BOT_ID_DISCORD", "the-bot")
        gateway = GatewayManager()
        raw = {
            "platform": "discord",
            "author": {"id": "the-bot"},
            "channel_id": "chanA",
            "content": "echo of my own post",
            "timestamp": time.time(),
            "id": "self-echo-1",
        }

        result = await gateway.normalize_message(raw)

        assert result is None

    @pytest.mark.asyncio
    async def test_duplicate_message_id_produces_exactly_one_pass_through(self):
        """The same (platform, channel, message_id) delivered twice yields
        exactly one message that would start an agent turn."""
        gateway = GatewayManager()
        raw = {
            "platform": "discord",
            "author": {"id": "user1"},
            "channel_id": "chanB",
            "content": "hi",
            "timestamp": time.time(),
            "id": "dup-check-1",
        }

        first = await gateway.normalize_message(dict(raw))
        second = await gateway.normalize_message(dict(raw))

        assert first is not None
        assert second is None

    @pytest.mark.asyncio
    async def test_chain_over_recursion_ceiling_is_halted(self):
        from services.gateway.ingest_governor import INGEST_MAX_CHAIN_DEPTH

        gateway = GatewayManager()
        raw = {
            "platform": "discord",
            "author": {"id": "agent-a"},
            "channel_id": "chanC",
            "content": "forwarded",
            "timestamp": time.time(),
            "id": "chain-check-1",
            "chain_depth": INGEST_MAX_CHAIN_DEPTH + 1,
        }

        result = await gateway.normalize_message(raw)

        assert result is None

    @pytest.mark.asyncio
    async def test_agent_to_agent_loop_terminates_across_a_real_platform_round_trip(self):
        """Simulates the actual failure mode from the issue: an agent-to-agent
        reply chain on a channel where NO real platform round-trips
        AutoBot-internal metadata -- every inbound webhook delivers a
        brand-new payload with no memory of prior turns, exactly like a real
        Discord/Slack/Telegram event. A payload field the platform never
        echoes back cannot be the recursion guard's source of truth; the
        guard must terminate the chain using state that survives the
        round-trip (#14028)."""
        from services.gateway.ingest_governor import INGEST_MAX_CHAIN_DEPTH

        gateway = GatewayManager()
        platform, channel = "discord", "loop-channel-rt"
        max_turns = INGEST_MAX_CHAIN_DEPTH + 5

        turns_survived = 0
        for i in range(max_turns):
            # A brand-new raw payload each turn, with no AutoBot-internal
            # field -- real platforms never round-trip one.
            raw = {
                "platform": platform,
                "author": {"id": "the-other-agent"},
                "channel_id": channel,
                "content": f"turn {i}",
                "timestamp": time.time(),
                "id": f"loop-rt-{i}",
            }
            unified = await gateway.normalize_message(raw)
            if unified is None:
                break
            turns_survived += 1

        assert turns_survived <= INGEST_MAX_CHAIN_DEPTH, (
            f"chain ran {turns_survived} turns with no platform ever carrying "
            "chain_depth in its payload -- the recursion guard did not terminate it"
        )

    @pytest.mark.asyncio
    async def test_normal_message_still_routes(self):
        """The governance stage must not break the working path."""
        gateway = GatewayManager()
        raw = {
            "platform": "discord",
            "author": {"id": "a-human"},
            "channel_id": "chanD",
            "content": "hello there",
            "timestamp": time.time(),
            "id": "normal-check-1",
        }

        result = await gateway.normalize_message(raw)

        assert result is not None
        assert result.message == "hello there"

    @pytest.mark.asyncio
    async def test_missing_message_id_is_rejected_fail_closed(self):
        gateway = GatewayManager()
        raw = {
            "platform": "web",
            "user_id": "webuser",
            "channel_id": "main",
            "message": "no id supplied",
            "timestamp": time.time(),
        }

        with pytest.raises(ValueError, match="missing required author id or message id"):
            await gateway.normalize_message(raw)
