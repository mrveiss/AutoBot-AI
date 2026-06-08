# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Webhook Authentication Security Tests (GH#9657)

Tests cover fail-closed authentication for:
- Telegram webhook (X-Telegram-Bot-Api-Secret-Token)
- AlertManager webhook (X-AlertManager-Secret)

Security requirements:
- 503 when secret not configured (fail-closed, not fail-open)
- 401 when authentication header missing
- 403 when authentication header invalid
- 200 when authentication succeeds

Target coverage: 100% of authentication paths
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient


class TestTelegramWebhookAuthentication:
    """Security tests for Telegram webhook authentication (GH#9657)"""

    @pytest.fixture
    def valid_telegram_update(self):
        """Sample valid Telegram update payload"""
        return {
            "update_id": 123456789,
            "message": {
                "message_id": 1,
                "from": {
                    "id": 123,
                    "is_bot": False,
                    "first_name": "Test",
                    "username": "testuser",
                },
                "chat": {"id": 123, "type": "private"},
                "date": 1234567890,
                "text": "Hello AutoBot",
            },
        }

    @pytest.mark.asyncio
    async def test_telegram_webhook_fails_closed_when_secret_not_configured(self, valid_telegram_update):
        """
        CRITICAL: Telegram webhook MUST return 503 when secret not configured.
        This is the core fail-closed fix from GH#9657.
        """

        # Mock get_telegram_webhook_secret to return None (not configured)
        with patch(
            "api.telegram_bot.get_telegram_webhook_secret",
            return_value=None,
        ):
            from main import app

            client = TestClient(app)

            response = client.post(
                "/api/telegram/webhook",
                json=valid_telegram_update,
                headers={"Content-Type": "application/json"},
            )

            # MUST fail closed with 503 (not 200 like before the fix)
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "not configured" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_telegram_webhook_returns_401_when_header_missing(self, valid_telegram_update):
        """
        Security: Telegram webhook MUST return 401 when X-Telegram-Bot-Api-Secret-Token missing.
        """
        with patch(
            "api.telegram_bot.get_telegram_webhook_secret",
            return_value="test_secret_123",
        ):
            from main import app

            client = TestClient(app)

            # Send request WITHOUT secret header
            response = client.post(
                "/api/telegram/webhook",
                json=valid_telegram_update,
                headers={"Content-Type": "application/json"},
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert "missing" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_telegram_webhook_returns_403_when_secret_invalid(self, valid_telegram_update):
        """
        Security: Telegram webhook MUST return 403 when secret is incorrect.
        """
        with patch(
            "api.telegram_bot.get_telegram_webhook_secret",
            return_value="correct_secret_123",
        ):
            from main import app

            client = TestClient(app)

            # Send request with WRONG secret
            response = client.post(
                "/api/telegram/webhook",
                json=valid_telegram_update,
                headers={
                    "Content-Type": "application/json",
                    "X-Telegram-Bot-Api-Secret-Token": "wrong_secret_456",
                },
            )

            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert "forbidden" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_telegram_webhook_succeeds_with_valid_authentication(self, valid_telegram_update):
        """
        Security: Telegram webhook MUST accept request with valid authentication.
        """
        with (
            patch(
                "api.telegram_bot.get_telegram_webhook_secret",
                return_value="correct_secret_123",
            ),
            patch("api.telegram_bot.gateway_manager") as mock_gateway,
            patch("api.telegram_bot._route_to_chat_and_reply", new_callable=AsyncMock),
        ):
            mock_gateway.normalize_message = AsyncMock(
                return_value=type(
                    "UnifiedMessage",
                    (),
                    {
                        "user_id": "123",
                        "channel_id": "123",
                        "message_text": "Hello",
                    },
                )()
            )

            from main import app

            client = TestClient(app)

            # Send request with CORRECT secret
            response = client.post(
                "/api/telegram/webhook",
                json=valid_telegram_update,
                headers={
                    "Content-Type": "application/json",
                    "X-Telegram-Bot-Api-Secret-Token": "correct_secret_123",
                },
            )

            assert response.status_code == status.HTTP_200_OK


class TestAlertManagerWebhookAuthentication:
    """Security tests for AlertManager webhook authentication (GH#9657)"""

    @pytest.fixture
    def valid_alertmanager_payload(self):
        """Sample valid AlertManager webhook payload"""
        return {
            "version": "4",
            "groupKey": '{}:{alertname="TestAlert"}',
            "truncatedAlerts": 0,
            "status": "firing",
            "receiver": "default",
            "groupLabels": {"alertname": "TestAlert"},
            "commonLabels": {"alertname": "TestAlert", "severity": "critical"},
            "commonAnnotations": {"summary": "Test alert"},
            "externalURL": "http://localhost:9093",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "TestAlert", "severity": "critical"},
                    "annotations": {"summary": "Test alert"},
                    "startsAt": "2026-01-01T12:00:00.000Z",
                    "generatorURL": "http://localhost:9090",
                    "fingerprint": "test123",
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_alertmanager_webhook_fails_closed_when_secret_not_configured(self, valid_alertmanager_payload):
        """
        CRITICAL: AlertManager webhook MUST return 503 when secret not configured.
        This prevents unauthenticated alert injection (GH#9657).
        """
        # Clear ALERTMANAGER_WEBHOOK_SECRET env var
        with patch.dict(os.environ, {}, clear=True):
            from main import app

            client = TestClient(app)

            response = client.post(
                "/api/webhook/alertmanager",
                json=valid_alertmanager_payload,
                headers={"Content-Type": "application/json"},
            )

            # MUST fail closed with 503
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "not configured" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_alertmanager_webhook_returns_401_when_header_missing(self, valid_alertmanager_payload):
        """
        Security: AlertManager webhook MUST return 401 when X-AlertManager-Secret missing.
        """
        with patch.dict(os.environ, {"ALERTMANAGER_WEBHOOK_SECRET": "test_secret_789"}):
            from main import app

            client = TestClient(app)

            # Send request WITHOUT secret header
            response = client.post(
                "/api/webhook/alertmanager",
                json=valid_alertmanager_payload,
                headers={"Content-Type": "application/json"},
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert "missing" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_alertmanager_webhook_returns_403_when_secret_invalid(self, valid_alertmanager_payload):
        """
        Security: AlertManager webhook MUST return 403 when secret is incorrect.
        """
        with patch.dict(os.environ, {"ALERTMANAGER_WEBHOOK_SECRET": "correct_secret_789"}):
            from main import app

            client = TestClient(app)

            # Send request with WRONG secret
            response = client.post(
                "/api/webhook/alertmanager",
                json=valid_alertmanager_payload,
                headers={
                    "Content-Type": "application/json",
                    "X-AlertManager-Secret": "wrong_secret_000",
                },
            )

            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert "invalid" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_alertmanager_webhook_succeeds_with_valid_authentication(self, valid_alertmanager_payload):
        """
        Security: AlertManager webhook MUST accept request with valid authentication.
        """
        with (
            patch.dict(os.environ, {"ALERTMANAGER_WEBHOOK_SECRET": "correct_secret_789"}),
            patch("api.alertmanager_webhook.ws_manager") as mock_ws,
        ):
            mock_ws.broadcast_update = AsyncMock()

            from main import app

            client = TestClient(app)

            # Send request with CORRECT secret
            response = client.post(
                "/api/webhook/alertmanager",
                json=valid_alertmanager_payload,
                headers={
                    "Content-Type": "application/json",
                    "X-AlertManager-Secret": "correct_secret_789",
                },
            )

            assert response.status_code == status.HTTP_200_OK
            assert response.json()["status"] == "success"


class TestWebhookSecurityDocumentation:
    """Verify security documentation exists for webhook authentication"""

    def test_telegram_webhook_docstring_mentions_security(self):
        """Telegram webhook docstring must mention security requirements"""
        from api.telegram_bot import telegram_webhook

        docstring = telegram_webhook.__doc__
        assert docstring is not None
        assert "security" in docstring.lower()
        assert "secret" in docstring.lower()

    def test_alertmanager_webhook_docstring_mentions_security(self):
        """AlertManager webhook docstring must mention security requirements"""
        from api.alertmanager_webhook import receive_alertmanager_webhook

        docstring = receive_alertmanager_webhook.__doc__
        assert docstring is not None
        assert "security" in docstring.lower() or "gh#9657" in docstring.lower()

    def test_env_example_documents_telegram_webhook_secret(self):
        """Verify .env.example documents TELEGRAM_WEBHOOK_SECRET"""
        env_example_path = "${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/.env.example"
        if not os.path.exists(env_example_path):
            pytest.skip(".env.example not found")

        with open(env_example_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Should document the Telegram webhook secret requirement
        assert "TELEGRAM_WEBHOOK_SECRET" in content or "telegram" in content.lower() and "webhook" in content.lower()

    def test_env_example_documents_alertmanager_webhook_secret(self):
        """Verify .env.example documents ALERTMANAGER_WEBHOOK_SECRET"""
        env_example_path = "${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/.env.example"
        if not os.path.exists(env_example_path):
            pytest.skip(".env.example not found")

        with open(env_example_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Should document the AlertManager webhook secret requirement
        assert (
            "ALERTMANAGER_WEBHOOK_SECRET" in content
            or "alertmanager" in content.lower()
            and "webhook" in content.lower()
        )


class TestWebhookSecurityRegression:
    """Regression tests to prevent re-introduction of fail-open vulnerability"""

    def test_telegram_webhook_does_not_return_200_when_secret_unset(self):
        """
        REGRESSION: Ensure Telegram webhook NEVER returns 200 when secret unset.
        This was the original vulnerability in GH#9657.
        """
        with patch(
            "api.telegram_bot.get_telegram_webhook_secret",
            return_value=None,
        ):
            from main import app

            client = TestClient(app)

            response = client.post(
                "/api/telegram/webhook",
                json={"update_id": 1, "message": {"message_id": 1}},
            )

            # MUST NOT be 200
            assert response.status_code != status.HTTP_200_OK
            # MUST be 503 (fail-closed)
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_alertmanager_webhook_does_not_return_200_when_secret_unset(self):
        """
        REGRESSION: Ensure AlertManager webhook NEVER returns 200 when secret unset.
        """
        with patch.dict(os.environ, {}, clear=True):
            from main import app

            client = TestClient(app)

            response = client.post(
                "/api/webhook/alertmanager",
                json={
                    "version": "4",
                    "status": "firing",
                    "receiver": "default",
                    "alerts": [],
                },
            )

            # MUST NOT be 200
            assert response.status_code != status.HTTP_200_OK
            # MUST be 503 (fail-closed)
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
