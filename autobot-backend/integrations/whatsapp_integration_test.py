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
from integrations.whatsapp_integration import WhatsAppIntegration


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
