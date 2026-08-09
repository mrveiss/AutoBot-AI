# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

# Repository root — this file lives at <root>/autobot-backend/api/.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEBHOOK_AUTH_DOC = PROJECT_ROOT / "docs" / "security" / "WEBHOOK_AUTHENTICATION.md"


@pytest.fixture(scope="module")
def client():
    """TestClient over the real backend application.

    Built through ``app_factory.create_app`` rather than ``from main import app``:
    the repo root ships a deprecated ``main.py`` shim that exposes no ``app``, and
    it wins over ``autobot-backend/main.py`` because ``pytest.ini`` puts ``.``
    ahead of ``autobot-backend`` on ``pythonpath``.

    Module-scoped so the app is built once and, critically, outside the
    ``patch.dict(os.environ, ..., clear=True)`` blocks the tests below use — the
    app must not be constructed with a wiped environment.
    """
    from app_factory import create_app

    return TestClient(create_app())


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
    async def test_telegram_webhook_fails_closed_when_secret_not_configured(self, client, valid_telegram_update):
        """
        CRITICAL: Telegram webhook MUST return 503 when secret not configured.
        This is the core fail-closed fix from GH#9657.
        """

        # Mock get_telegram_webhook_secret to return None (not configured)
        with patch(
            "api.telegram_bot.get_telegram_webhook_secret",
            return_value=None,
        ):
            response = client.post(
                "/api/telegram/webhook",
                json=valid_telegram_update,
                headers={"Content-Type": "application/json"},
            )

            # MUST fail closed with 503 (not 200 like before the fix)
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "not configured" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_telegram_webhook_returns_401_when_header_missing(self, client, valid_telegram_update):
        """
        Security: Telegram webhook MUST return 401 when X-Telegram-Bot-Api-Secret-Token missing.
        """
        with patch(
            "api.telegram_bot.get_telegram_webhook_secret",
            return_value="test_secret_123",
        ):
            # Send request WITHOUT secret header
            response = client.post(
                "/api/telegram/webhook",
                json=valid_telegram_update,
                headers={"Content-Type": "application/json"},
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert "missing" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_telegram_webhook_returns_403_when_secret_invalid(self, client, valid_telegram_update):
        """
        Security: Telegram webhook MUST return 403 when secret is incorrect.
        """
        with patch(
            "api.telegram_bot.get_telegram_webhook_secret",
            return_value="correct_secret_123",
        ):
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
    async def test_telegram_webhook_succeeds_with_valid_authentication(self, client, valid_telegram_update):
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
                    "GatewayMessage",
                    (),
                    {
                        "user_id": "123",
                        "channel_id": "123",
                        "message_text": "Hello",
                    },
                )()
            )
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
            "externalURL": "http://localhost:9093",  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "TestAlert", "severity": "critical"},
                    "annotations": {"summary": "Test alert"},
                    "startsAt": "2026-01-01T12:00:00.000Z",
                    "generatorURL": "http://localhost:9090",  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
                    "fingerprint": "test123",
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_alertmanager_webhook_fails_closed_when_secret_not_configured(
        self, client, valid_alertmanager_payload
    ):
        """
        CRITICAL: AlertManager webhook MUST return 503 when secret not configured.
        This prevents unauthenticated alert injection (GH#9657).
        """
        # Clear ALERTMANAGER_WEBHOOK_SECRET env var
        with patch.dict(os.environ, {}, clear=True):
            response = client.post(
                "/api/webhook/alertmanager",
                json=valid_alertmanager_payload,
                headers={"Content-Type": "application/json"},
            )

            # MUST fail closed with 503
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "not configured" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_alertmanager_webhook_returns_401_when_header_missing(self, client, valid_alertmanager_payload):
        """
        Security: AlertManager webhook MUST return 401 when X-AlertManager-Secret missing.
        """
        with patch.dict(os.environ, {"ALERTMANAGER_WEBHOOK_SECRET": "test_secret_789"}):
            # Send request WITHOUT secret header
            response = client.post(
                "/api/webhook/alertmanager",
                json=valid_alertmanager_payload,
                headers={"Content-Type": "application/json"},
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert "missing" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_alertmanager_webhook_returns_403_when_secret_invalid(self, client, valid_alertmanager_payload):
        """
        Security: AlertManager webhook MUST return 403 when secret is incorrect.
        """
        with patch.dict(os.environ, {"ALERTMANAGER_WEBHOOK_SECRET": "correct_secret_789"}):
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
    async def test_alertmanager_webhook_succeeds_with_valid_authentication(self, client, valid_alertmanager_payload):
        """
        Security: AlertManager webhook MUST accept request with valid authentication.
        """
        with (
            patch.dict(os.environ, {"ALERTMANAGER_WEBHOOK_SECRET": "correct_secret_789"}),
            patch("api.alertmanager_webhook.ws_manager") as mock_ws,
        ):
            mock_ws.broadcast_update = AsyncMock()
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

    def test_operator_docs_document_telegram_webhook_secret(self):
        """The Telegram webhook secret must be documented for operators.

        Replaces a pair of tests that read
        ``"${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/.env.example"`` —
        shell syntax Python never expands, so the file was never found and both
        tests always skipped (#13149 class of defect). They also asserted the
        wrong premise: the Telegram secret is not an environment variable at all,
        it is generated per bot and stored server-side. The canonical operator
        reference is asserted instead, resolved from this file's own location.
        """
        content = WEBHOOK_AUTH_DOC.read_text(encoding="utf-8")

        assert "X-Telegram-Bot-Api-Secret-Token" in content
        assert "503 Service Unavailable" in content

    def test_operator_docs_document_alertmanager_webhook_secret(self):
        """The AlertManager webhook secret must be documented for operators."""
        content = WEBHOOK_AUTH_DOC.read_text(encoding="utf-8")

        assert "ALERTMANAGER_WEBHOOK_SECRET" in content
        assert "X-AlertManager-Secret" in content


class TestWebhookSecurityRegression:
    """Regression tests to prevent re-introduction of fail-open vulnerability"""

    def test_telegram_webhook_does_not_return_200_when_secret_unset(self, client):
        """
        REGRESSION: Ensure Telegram webhook NEVER returns 200 when secret unset.
        This was the original vulnerability in GH#9657.
        """
        with patch(
            "api.telegram_bot.get_telegram_webhook_secret",
            return_value=None,
        ):
            response = client.post(
                "/api/telegram/webhook",
                json={"update_id": 1, "message": {"message_id": 1}},
            )

            # MUST NOT be 200
            assert response.status_code != status.HTTP_200_OK
            # MUST be 503 (fail-closed)
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @pytest.mark.parametrize(
        "body",
        [None, [1, 2, 3], {"not": "an update"}],
        ids=["no-body", "wrong-type", "unexpected-shape"],
    )
    def test_telegram_webhook_authenticates_before_parsing_body(self, client, body):
        """
        REGRESSION: authentication MUST run before FastAPI validates the body.

        With the check inside the handler, an unauthenticated caller who sent a
        body FastAPI rejected got a 422 schema error instead of failing closed —
        an unauthenticated payload-schema oracle. Auth is now a route dependency,
        so every unauthenticated shape fails closed regardless of the body.
        """
        with patch("api.telegram_bot.get_telegram_webhook_secret", return_value=None):
            response = client.post("/api/telegram/webhook", json=body)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "not configured" in response.json()["detail"].lower()

    @pytest.mark.parametrize(
        "body",
        [None, [1, 2, 3], {"not": "an alert"}],
        ids=["no-body", "wrong-type", "unexpected-shape"],
    )
    def test_alertmanager_webhook_authenticates_before_parsing_body(self, client, body):
        """
        REGRESSION: AlertManager authentication MUST run before body validation.
        """
        with patch.dict(os.environ, {}, clear=True):
            response = client.post("/api/webhook/alertmanager", json=body)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "not configured" in response.json()["detail"].lower()

    def test_alertmanager_webhook_does_not_return_200_when_secret_unset(self, client):
        """
        REGRESSION: Ensure AlertManager webhook NEVER returns 200 when secret unset.
        """
        with patch.dict(os.environ, {}, clear=True):
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
