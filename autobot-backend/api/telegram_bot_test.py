# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Wiring tests for the Telegram bot channel route (Issue #9006).

These verify the inbound path is actually reachable and dispatched:
- the router is registered exactly once (core registry; NOT duplicated in the
  integration registry, which would double-mount the routes),
- the webhook/config routes are exposed,
- the gateway TelegramAdapter normalizes a raw Telegram Update into a
  UnifiedMessage (text, command, and file attachments),
- command handling produces the expected replies.
"""

from types import SimpleNamespace

import pytest

from initialization.router_registry.integration_routers import INTEGRATION_ROUTER_CONFIGS


class TestRouterRegistration:
    """The Telegram webhook router must be registered exactly once to be reachable."""

    def test_telegram_router_in_core_registry(self):
        from initialization.router_registry.core_routers import load_core_routers

        names = [name for (_router, _prefix, _tags, name) in load_core_routers()]
        assert "telegram_bot" in names

    def test_telegram_not_duplicated_in_integration_registry(self):
        # Telegram is mounted via core_routers; a second entry here would
        # double-mount /telegram/* routes and OpenAPI operations (GH#9006).
        module_paths = [cfg[0] for cfg in INTEGRATION_ROUTER_CONFIGS]
        assert "api.telegram_bot" not in module_paths

    def test_telegram_router_exposes_routes(self):
        from api import telegram_bot

        assert hasattr(telegram_bot, "router")
        paths = {route.path for route in telegram_bot.router.routes}
        assert "/telegram/webhook" in paths
        assert "/telegram/config" in paths


class TestGatewayNormalization:
    """A raw Telegram Update normalizes through the gateway TelegramAdapter."""

    def _gateway(self):
        from services.gateway.gateway_manager import GatewayManager

        return GatewayManager()

    @pytest.mark.asyncio
    async def test_text_message_normalizes(self):
        raw = {
            "platform": "telegram",
            "message": {
                "message_id": 11,
                "date": 1700000000,
                "chat": {"id": 4242, "type": "private"},
                "from": {"id": 99},
                "text": "hi bot",
            },
        }
        unified = await self._gateway().normalize_message(raw)
        assert unified.platform == "telegram"
        assert unified.user_id == "99"
        assert unified.channel_id == "4242"
        assert unified.message == "hi bot"
        assert unified.metadata.get("is_command") is not True

    @pytest.mark.asyncio
    async def test_command_message_normalizes(self):
        raw = {
            "platform": "telegram",
            "message": {
                "message_id": 12,
                "date": 1700000001,
                "chat": {"id": 4242, "type": "private"},
                "from": {"id": 99},
                "text": "/status now",
            },
        }
        unified = await self._gateway().normalize_message(raw)
        assert unified.metadata.get("is_command") is True
        assert unified.metadata.get("command") == "status"
        assert unified.metadata.get("command_args") == ["now"]

    @pytest.mark.asyncio
    async def test_document_attachment_normalizes(self):
        raw = {
            "platform": "telegram",
            "message": {
                "message_id": 13,
                "date": 1700000002,
                "chat": {"id": 4242, "type": "private"},
                "from": {"id": 99},
                "document": {"file_id": "doc-1", "file_name": "x.pdf", "mime_type": "application/pdf"},
            },
        }
        unified = await self._gateway().normalize_message(raw)
        assert unified.metadata.get("has_file") is True
        assert unified.metadata.get("file_id") == "doc-1"
        assert unified.metadata.get("file_type") == "document"


class TestCommandHandling:
    """Basic command handling (/help, /status) returns user-facing replies (GH#9006 AC)."""

    @pytest.mark.asyncio
    async def test_status_command(self):
        from api.telegram_bot import _handle_command

        reply = await _handle_command("status", [], chat_id="4242", message_id=1)
        assert reply is not None and "online" in reply.lower()

    @pytest.mark.asyncio
    async def test_help_command_lists_commands(self):
        from api.telegram_bot import _handle_command

        reply = await _handle_command("help", [], chat_id="4242", message_id=1)
        assert reply is not None
        assert "/status" in reply and "/help" in reply

    @pytest.mark.asyncio
    async def test_unknown_command_returns_none(self):
        from api.telegram_bot import _handle_command

        reply = await _handle_command("nope", [], chat_id="4242", message_id=1)
        assert reply is None


class TestCaptionlessMediaRouting:
    """Caption-less media must not crash ChatMessage construction (GH#10483)."""

    @pytest.mark.asyncio
    async def test_captionless_attachment_gets_placeholder_content(self, monkeypatch):
        from api import telegram_bot as tg
        from services.gateway.gateway_manager import GatewayManager

        captured: dict = {}

        async def fake_process(message, **kwargs):
            captured["message"] = message
            return SimpleNamespace(content="ack")

        async def fake_send(*args, **kwargs):
            captured["sent"] = True

        # Lazily-imported deps are patched at their source modules.
        monkeypatch.setattr("api.chat.process_chat_message", fake_process)
        monkeypatch.setattr(tg, "send_telegram_response", fake_send)
        monkeypatch.setattr("utils.chat_utils.get_chat_history_manager", lambda req: object())
        monkeypatch.setattr("utils.lazy_singleton.lazy_init_singleton", lambda state, name, cls: object())

        # A document with no caption normalizes to an empty message + has_file.
        unified = await GatewayManager().normalize_message(
            {
                "platform": "telegram",
                "message": {
                    "message_id": 21,
                    "date": 1700000003,
                    "chat": {"id": 4242, "type": "private"},
                    "from": {"id": 99},
                    "document": {"file_id": "doc-9", "file_name": "x.pdf", "mime_type": "application/pdf"},
                },
            }
        )
        assert unified.message == ""
        assert unified.metadata.get("has_file") is True

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        # Without the fix this raises pydantic ValidationError (content min_length=1).
        await tg._route_to_chat_and_reply(request, unified)

        assert captured["message"].content == "[document attachment]"
        assert captured.get("sent") is True
