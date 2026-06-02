# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for new channel adapters: Telegram, Signal, Matrix, iMessage

Covers:
- Message normalization to unified schema
- Response denormalization to platform format
- Rate limit configuration
- Env-gated adapters (Signal, iMessage) behave correctly when disabled
- E2EE metadata preserved in Matrix adapter
- Thread/reply context in metadata
- All adapters registered in GatewayManager (9+ platforms)
- Performance: <50ms per normalize call
"""

import time

import pytest

from services.gateway import (
    GatewayManager,
    IMessageAdapter,
    MatrixAdapter,
    NormalizedResponse,
    SignalAdapter,
    TelegramAdapter,
    UnifiedMessage,
)


class TestTelegramAdapter:
    """Test Telegram platform adapter."""

    @pytest.fixture
    def adapter(self):
        return TelegramAdapter()

    @pytest.mark.asyncio
    async def test_normalize_private_message(self, adapter):
        raw = {
            "message": {
                "from": {"id": 123456, "username": "alice"},
                "chat": {"id": -9001, "type": "private"},
                "text": "Hello from Telegram",
                "date": 1700000000,
                "message_id": 42,
            }
        }
        unified = await adapter.normalize_message(raw)
        assert isinstance(unified, UnifiedMessage)
        assert unified.platform == "telegram"
        assert unified.user_id == "123456"
        assert unified.channel_id == "-9001"
        assert unified.message == "Hello from Telegram"
        assert unified.timestamp == 1700000000.0
        assert unified.metadata["message_id"] == 42
        assert unified.metadata["is_reply"] is False

    @pytest.mark.asyncio
    async def test_normalize_group_reply(self, adapter):
        raw = {
            "message": {
                "from": {"id": 789, "username": "bob"},
                "chat": {"id": -100123, "type": "supergroup"},
                "text": "Reply text",
                "date": 1700000100,
                "message_id": 55,
                "reply_to_message": {"message_id": 44},
            }
        }
        unified = await adapter.normalize_message(raw)
        assert unified.metadata["is_reply"] is True
        assert unified.metadata["reply_to_message_id"] == 44
        assert unified.metadata["chat_type"] == "supergroup"

    @pytest.mark.asyncio
    async def test_denormalize_response(self, adapter):
        response = NormalizedResponse(
            platform="telegram",
            channel_id="-9001",
            user_id="123456",
            content="Hello back",
            response_type="message",
            metadata={},
        )
        payload = await adapter.denormalize_response(response)
        assert payload["chat_id"] == "-9001"
        assert payload["text"] == "Hello back"
        assert payload["parse_mode"] == "Markdown"

    @pytest.mark.asyncio
    async def test_denormalize_thread_reply(self, adapter):
        response = NormalizedResponse(
            platform="telegram",
            channel_id="-9001",
            user_id="123456",
            content="Reply",
            response_type="thread_reply",
            metadata={"message_id": 42},
        )
        payload = await adapter.denormalize_response(response)
        assert payload["reply_to_message_id"] == 42

    @pytest.mark.asyncio
    async def test_denormalize_photo_response(self, adapter):
        """Test denormalization sets _api_method for photo responses (MVA-2373)."""
        response = NormalizedResponse(
            platform="telegram",
            channel_id="-9001",
            user_id="123456",
            content="Check this photo",
            response_type="message",
            metadata={"file_id": "AgACAgIAAxkBAAIC", "file_type": "photo"},
        )
        payload = await adapter.denormalize_response(response)
        assert payload["_api_method"] == "sendPhoto"
        assert payload["photo"] == "AgACAgIAAxkBAAIC"
        assert payload["caption"] == "Check this photo"
        assert payload["parse_mode"] == "Markdown"
        assert "text" not in payload

    @pytest.mark.asyncio
    async def test_denormalize_document_response(self, adapter):
        """Test denormalization sets _api_method for document responses (MVA-2373)."""
        response = NormalizedResponse(
            platform="telegram",
            channel_id="-9001",
            user_id="123456",
            content="Here's the file",
            response_type="message",
            metadata={"file_id": "BQACAgIAAxkBAAIC", "file_type": "document"},
        )
        payload = await adapter.denormalize_response(response)
        assert payload["_api_method"] == "sendDocument"
        assert payload["document"] == "BQACAgIAAxkBAAIC"
        assert payload["caption"] == "Here's the file"
        assert payload["parse_mode"] == "Markdown"
        assert "text" not in payload

    @pytest.mark.asyncio
    async def test_denormalize_text_sets_api_method(self, adapter):
        """Test denormalization sets _api_method for text messages (MVA-2373)."""
        response = NormalizedResponse(
            platform="telegram",
            channel_id="-9001",
            user_id="123456",
            content="Just text",
            response_type="message",
            metadata={},
        )
        payload = await adapter.denormalize_response(response)
        assert payload["_api_method"] == "sendMessage"
        assert payload["text"] == "Just text"
        assert "photo" not in payload
        assert "document" not in payload

    def test_rate_limit(self, adapter):
        limits = adapter.get_rate_limit()
        assert limits["requests_per_second"] == 30
        assert limits["burst_size"] == 30

    @pytest.mark.asyncio
    async def test_performance(self, adapter):
        raw = {
            "message": {
                "from": {"id": 1},
                "chat": {"id": 1, "type": "private"},
                "text": "perf test",
                "date": 1700000000,
                "message_id": 1,
            }
        }
        start = time.time()
        await adapter.normalize_message(raw)
        assert (time.time() - start) * 1000 < 50


class TestSignalAdapter:
    """Test Signal platform adapter."""

    @pytest.fixture
    def adapter(self):
        return SignalAdapter()

    @pytest.mark.asyncio
    async def test_normalize_dm(self, adapter):
        raw = {
            "envelope": {
                "source": "+14155551234",
                "dataMessage": {
                    "timestamp": 1700000000000,
                    "message": "Hello Signal",
                },
            }
        }
        unified = await adapter.normalize_message(raw)
        assert unified.platform == "signal"
        assert unified.user_id == "+14155551234"
        assert unified.channel_id == "+14155551234"
        assert unified.message == "Hello Signal"
        assert unified.metadata["e2ee"] is True
        assert unified.metadata["is_group"] is False

    @pytest.mark.asyncio
    async def test_normalize_group_message(self, adapter):
        raw = {
            "envelope": {
                "source": "+14155551234",
                "dataMessage": {
                    "timestamp": 1700000001000,
                    "message": "Group msg",
                    "groupInfo": {"groupId": "abc123group"},
                },
            }
        }
        unified = await adapter.normalize_message(raw)
        assert unified.channel_id == "abc123group"
        assert unified.metadata["is_group"] is True
        assert unified.metadata["group_id"] == "abc123group"

    @pytest.mark.asyncio
    async def test_denormalize_when_disabled(self, adapter, monkeypatch):
        monkeypatch.setattr(adapter, "_enabled", False)
        response = NormalizedResponse(
            platform="signal",
            channel_id="+14155551234",
            user_id="+14155551234",
            content="test",
            response_type="message",
            metadata={},
        )
        payload = await adapter.denormalize_response(response)
        assert payload["_signal_disabled"] is True
        assert payload["content"] == "test"

    @pytest.mark.asyncio
    async def test_denormalize_when_enabled(self, adapter, monkeypatch):
        monkeypatch.setattr(adapter, "_enabled", True)
        response = NormalizedResponse(
            platform="signal",
            channel_id="+14155551234",
            user_id="+14155551234",
            content="Hello",
            response_type="message",
            metadata={},
        )
        payload = await adapter.denormalize_response(response)
        assert payload["recipient"] == "+14155551234"
        assert payload["message"] == "Hello"

    def test_rate_limit(self, adapter):
        limits = adapter.get_rate_limit()
        assert limits["requests_per_second"] == 1
        assert limits["burst_size"] == 5

    @pytest.mark.asyncio
    async def test_performance(self, adapter):
        raw = {
            "envelope": {
                "source": "+1",
                "dataMessage": {"timestamp": 1700000000000, "message": "perf"},
            }
        }
        start = time.time()
        await adapter.normalize_message(raw)
        assert (time.time() - start) * 1000 < 50


class TestMatrixAdapter:
    """Test Matrix platform adapter."""

    @pytest.fixture
    def adapter(self):
        return MatrixAdapter()

    @pytest.mark.asyncio
    async def test_normalize_room_message(self, adapter):
        raw = {
            "event_id": "$abc123",
            "sender": "@alice:matrix.org",
            "room_id": "!room123:matrix.org",
            "content": {"msgtype": "m.text", "body": "Hello Matrix"},
            "origin_server_ts": 1700000000000,
        }
        unified = await adapter.normalize_message(raw)
        assert unified.platform == "matrix"
        assert unified.user_id == "@alice:matrix.org"
        assert unified.channel_id == "!room123:matrix.org"
        assert unified.message == "Hello Matrix"
        assert unified.timestamp == 1700000000.0
        assert unified.metadata["event_id"] == "$abc123"
        assert unified.metadata["msgtype"] == "m.text"

    @pytest.mark.asyncio
    async def test_normalize_thread_reply(self, adapter):
        raw = {
            "event_id": "$reply456",
            "sender": "@bob:matrix.org",
            "room_id": "!room123:matrix.org",
            "content": {
                "msgtype": "m.text",
                "body": "Thread reply",
                "m.relates_to": {
                    "rel_type": "m.thread",
                    "event_id": "$thread_root",
                },
            },
            "origin_server_ts": 1700000001000,
        }
        unified = await adapter.normalize_message(raw)
        assert unified.metadata["thread_id"] == "$thread_root"

    @pytest.mark.asyncio
    async def test_e2ee_flag_in_metadata(self, adapter, monkeypatch):
        monkeypatch.setattr(adapter, "_e2ee", True)
        raw = {
            "event_id": "$e",
            "sender": "@a:m.org",
            "room_id": "!r:m.org",
            "content": {"msgtype": "m.text", "body": "encrypted msg"},
            "origin_server_ts": 1700000000000,
        }
        unified = await adapter.normalize_message(raw)
        assert unified.metadata["e2ee"] is True

    @pytest.mark.asyncio
    async def test_denormalize_plain_message(self, adapter):
        response = NormalizedResponse(
            platform="matrix",
            channel_id="!room:m.org",
            user_id="@a:m.org",
            content="Reply",
            response_type="message",
            metadata={},
        )
        payload = await adapter.denormalize_response(response)
        assert payload["room_id"] == "!room:m.org"
        assert payload["content"]["body"] == "Reply"
        assert payload["content"]["msgtype"] == "m.text"

    @pytest.mark.asyncio
    async def test_denormalize_thread_reply(self, adapter):
        response = NormalizedResponse(
            platform="matrix",
            channel_id="!room:m.org",
            user_id="@a:m.org",
            content="Thread reply",
            response_type="thread_reply",
            metadata={"event_id": "$orig"},
        )
        payload = await adapter.denormalize_response(response)
        assert "m.relates_to" in payload["content"]

    def test_rate_limit(self, adapter):
        limits = adapter.get_rate_limit()
        assert limits["requests_per_second"] == 10
        assert limits["burst_size"] == 20

    @pytest.mark.asyncio
    async def test_performance(self, adapter):
        raw = {
            "event_id": "$x",
            "sender": "@a:m.org",
            "room_id": "!r:m.org",
            "content": {"msgtype": "m.text", "body": "perf"},
            "origin_server_ts": 1700000000000,
        }
        start = time.time()
        await adapter.normalize_message(raw)
        assert (time.time() - start) * 1000 < 50


class TestIMessageAdapter:
    """Test iMessage platform adapter."""

    @pytest.fixture
    def adapter(self):
        return IMessageAdapter()

    @pytest.mark.asyncio
    async def test_normalize_dm(self, adapter):
        raw = {
            "sender": "+14155551234",
            "chat_id": "+14155551234",
            "text": "Hello iMessage",
            "timestamp": 1700000000.0,
            "id": "msg-guid-abc",
        }
        unified = await adapter.normalize_message(raw)
        assert unified.platform == "imessage"
        assert unified.user_id == "+14155551234"
        assert unified.channel_id == "+14155551234"
        assert unified.message == "Hello iMessage"
        assert unified.metadata["macos_only"] is True

    @pytest.mark.asyncio
    async def test_normalize_group_chat(self, adapter):
        raw = {
            "sender": "+14155551234",
            "room_name": "chat12345678",
            "text": "Group message",
            "timestamp": 1700000000.0,
            "is_group": True,
        }
        unified = await adapter.normalize_message(raw)
        assert unified.channel_id == "chat12345678"
        assert unified.metadata["is_group"] is True

    @pytest.mark.asyncio
    async def test_denormalize_when_disabled(self, adapter, monkeypatch):
        monkeypatch.setattr(adapter, "_send_enabled", False)
        response = NormalizedResponse(
            platform="imessage",
            channel_id="+1",
            user_id="+1",
            content="test",
            response_type="message",
            metadata={},
        )
        payload = await adapter.denormalize_response(response)
        assert payload["_imessage_disabled"] is True
        assert payload["content"] == "test"

    @pytest.mark.asyncio
    async def test_denormalize_when_enabled(self, adapter, monkeypatch):
        monkeypatch.setattr(adapter, "_send_enabled", True)
        response = NormalizedResponse(
            platform="imessage",
            channel_id="+14155551234",
            user_id="+14155551234",
            content="Hello",
            response_type="message",
            metadata={"service": "iMessage"},
        )
        payload = await adapter.denormalize_response(response)
        assert payload["recipient"] == "+14155551234"
        assert payload["message"] == "Hello"
        assert payload["service"] == "iMessage"

    def test_rate_limit(self, adapter):
        limits = adapter.get_rate_limit()
        assert limits["requests_per_second"] == 1
        assert limits["burst_size"] == 3

    @pytest.mark.asyncio
    async def test_performance(self, adapter):
        raw = {
            "sender": "+1",
            "chat_id": "+1",
            "text": "perf",
            "timestamp": 1700000000.0,
        }
        start = time.time()
        await adapter.normalize_message(raw)
        assert (time.time() - start) * 1000 < 50


class TestGatewayManagerNinePlusPlatforms:
    """Verify GatewayManager registers 9+ platform adapters."""

    @pytest.fixture
    def gateway(self):
        return GatewayManager()

    def test_nine_plus_platforms_registered(self, gateway):
        platforms = set(gateway.get_supported_platforms())
        expected = {"web", "slack", "discord", "whatsapp", "teams", "telegram", "signal", "matrix", "imessage"}
        assert expected.issubset(platforms)
        assert len(platforms) >= 9

    @pytest.mark.asyncio
    async def test_normalize_telegram_through_gateway(self, gateway):
        raw = {
            "platform": "telegram",
            "message": {
                "from": {"id": 1},
                "chat": {"id": 1, "type": "private"},
                "text": "hi",
                "date": 1700000000,
                "message_id": 1,
            },
        }
        start = time.time()
        unified = await gateway.normalize_message(raw)
        assert unified.platform == "telegram"
        assert (time.time() - start) * 1000 < 50

    @pytest.mark.asyncio
    async def test_normalize_signal_through_gateway(self, gateway):
        raw = {
            "platform": "signal",
            "envelope": {
                "source": "+1",
                "dataMessage": {"timestamp": 1700000000000, "message": "hi"},
            },
        }
        unified = await gateway.normalize_message(raw)
        assert unified.platform == "signal"

    @pytest.mark.asyncio
    async def test_normalize_matrix_through_gateway(self, gateway):
        raw = {
            "platform": "matrix",
            "event_id": "$x",
            "sender": "@a:m.org",
            "room_id": "!r:m.org",
            "content": {"msgtype": "m.text", "body": "hi"},
            "origin_server_ts": 1700000000000,
        }
        unified = await gateway.normalize_message(raw)
        assert unified.platform == "matrix"

    @pytest.mark.asyncio
    async def test_normalize_imessage_through_gateway(self, gateway):
        raw = {
            "platform": "imessage",
            "sender": "+1",
            "chat_id": "+1",
            "text": "hi",
            "timestamp": 1700000000.0,
        }
        unified = await gateway.normalize_message(raw)
        assert unified.platform == "imessage"
