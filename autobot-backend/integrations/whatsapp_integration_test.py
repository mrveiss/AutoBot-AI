# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for WhatsApp Business API Integration (Issue #9007)
"""

from unittest.mock import AsyncMock

import pytest

from integrations.base import IntegrationConfig, IntegrationStatus
from integrations.whatsapp_integration import WhatsAppIntegration, _mask_phone


class TestMaskPhone:
    """_mask_phone redacts PII phone numbers for logging (GH#9725)."""

    def test_keeps_last_four_digits(self):
        assert _mask_phone("+15551234567") == "***4567"

    def test_strips_non_digits_before_masking(self):
        assert _mask_phone("+1 (555) 123-4567") == "***4567"

    def test_short_numbers_fully_masked(self):
        assert _mask_phone("1234") == "***"
        assert _mask_phone("12") == "***"

    def test_empty_and_none(self):
        assert _mask_phone("") == "<none>"
        assert _mask_phone(None) == "<none>"

    def test_full_number_never_appears_in_output(self):
        full = "+15551234567"
        assert full not in _mask_phone(full)
        assert "555123" not in _mask_phone(full)


@pytest.fixture
def whatsapp_config():
    """Create a test WhatsApp integration config."""
    return IntegrationConfig(
        name="whatsapp",
        provider="whatsapp",
        api_key="test-mock-token",
        base_url="https://graph.facebook.com/v18.0",
        extra={
            "phone_number_id": "123456789",
            "business_account_id": "987654321",
        },
    )


@pytest.fixture
def whatsapp_integration(whatsapp_config):
    """Create a test WhatsApp integration instance."""
    return WhatsAppIntegration(whatsapp_config)


class TestConnection:
    """Test connection health check."""

    @pytest.mark.asyncio
    async def test_connection_success(self, whatsapp_integration):
        """Connection test succeeds with valid credentials."""
        whatsapp_integration._make_request = AsyncMock(
            return_value={
                "status_code": 200,
                "body": {
                    "id": "123456789",
                    "display_phone_number": "+1234567890",
                    "verified_name": "Test Business",
                },
            }
        )

        health = await whatsapp_integration.test_connection()

        assert health.status == IntegrationStatus.CONNECTED
        assert "Test Business" in health.details.get("verified_name", "")


class TestSendTextMessage:
    """Test sending text messages."""

    @pytest.mark.asyncio
    async def test_send_text_message_success(self, whatsapp_integration):
        """Text message sends successfully to opted-in user."""
        whatsapp_integration.check_opt_in_status = AsyncMock(return_value={"opted_in": True})
        whatsapp_integration._make_request = AsyncMock(
            return_value={
                "status_code": 200,
                "body": {
                    "messages": [{"id": "wamid.test123"}],
                    "messaging_product": "whatsapp",
                },
            }
        )

        params = {
            "to": "+1234567890",
            "body": "Hello from AutoBot!",
        }

        result = await whatsapp_integration.send_text_message(params)

        assert result["ok"] is True
        assert result["message_id"] == "wamid.test123"


class TestReturnDictPhoneMasking:
    """Return dicts must not leak the full phone number (#9788).

    The masking must be at the API-return boundary only — the request payload
    sent to WhatsApp and the Redis-persisted record keep the real number.
    """

    @pytest.mark.asyncio
    async def test_send_text_masks_returned_to_but_payload_keeps_real_number(
        self, whatsapp_integration
    ):
        whatsapp_integration.check_opt_in_status = AsyncMock(return_value={"opted_in": True})
        whatsapp_integration._make_request = AsyncMock(
            return_value={
                "status_code": 200,
                "body": {"messages": [{"id": "wamid.test123"}]},
            }
        )

        result = await whatsapp_integration.send_text_message(
            {"to": "+1234567890", "body": "hi"}
        )

        # Return echoes only the masked number.
        assert result["to"] == _mask_phone("+1234567890") == "***7890"
        assert "+1234567890" not in str(result)
        # But the actual outbound request used the real number.
        sent_payload = whatsapp_integration._make_request.call_args.kwargs["json_data"]
        assert sent_payload["to"] == "+1234567890"

    @pytest.mark.asyncio
    async def test_send_text_error_return_masks_to(self, whatsapp_integration):
        whatsapp_integration.check_opt_in_status = AsyncMock(
            return_value={"opted_in": False}
        )
        result = await whatsapp_integration.send_text_message(
            {"to": "+1234567890", "body": "hi"}
        )
        assert result["ok"] is False
        assert result["to"] == "***7890"
        assert "+1234567890" not in str(result)

    @pytest.mark.asyncio
    async def test_check_opt_in_status_masks_returned_phone_number(
        self, whatsapp_integration, monkeypatch
    ):
        # Redis unavailable → early return path carries phone_number.
        monkeypatch.setattr(
            "integrations.whatsapp_integration.get_async_redis_client",
            AsyncMock(return_value=None),
        )
        result = await whatsapp_integration.check_opt_in_status(
            {"phone_number": "+1234567890"}
        )
        assert result["phone_number"] == "***7890"
        assert "+1234567890" not in str(result)
