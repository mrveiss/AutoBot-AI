# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Wiring tests for the WhatsApp channel route (Issue #9007).

These verify the inbound path is actually reachable and secured:
- the router is registered in the integration router registry,
- Meta webhook signatures are verified (fail-closed),
- Meta's nested webhook envelope is flattened into adapter-ready messages,
- the gateway WhatsAppAdapter normalizes the flattened message.
"""

import hashlib
import hmac
import json

import pytest

from initialization.router_registry.integration_routers import INTEGRATION_ROUTER_CONFIGS
from services.whatsapp_service import flatten_messages, verify_webhook_signature


class TestRouterRegistration:
    """The WhatsApp webhook router must be registered to be reachable."""

    def test_whatsapp_router_registered(self):
        module_paths = [cfg[0] for cfg in INTEGRATION_ROUTER_CONFIGS]
        assert "api.whatsapp" in module_paths

    def test_whatsapp_router_exposes_router(self):
        from api import whatsapp

        assert hasattr(whatsapp, "router")
        paths = {route.path for route in whatsapp.router.routes}
        assert "/whatsapp/webhook" in paths
        assert "/whatsapp/config" in paths


class TestSignatureVerification:
    """X-Hub-Signature-256 HMAC verification (Meta security requirement)."""

    def _sign(self, payload: bytes, secret: str) -> str:
        digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_valid_signature_accepted(self):
        body = b'{"object":"whatsapp_business_account"}'
        secret = "top-secret"  # nosec B105 - test fixture
        assert verify_webhook_signature(body, self._sign(body, secret), secret) is True

    def test_tampered_body_rejected(self):
        secret = "top-secret"  # nosec B105 - test fixture
        sig = self._sign(b"original", secret)
        assert verify_webhook_signature(b"tampered", sig, secret) is False

    def test_missing_header_rejected(self):
        assert verify_webhook_signature(b"x", None, "secret") is False

    def test_missing_secret_rejected(self):
        body = b"x"
        assert verify_webhook_signature(body, self._sign(body, "secret"), "") is False

    def test_malformed_header_prefix_rejected(self):
        assert verify_webhook_signature(b"x", "md5=deadbeef", "secret") is False


class TestFlattenMessages:
    """Meta's nested envelope is flattened into adapter-ready dicts."""

    def _meta_payload(self, body_text: str) -> dict:
        return {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "15551234567",
                                        "id": "wamid.ABC",
                                        "timestamp": "1700000000",
                                        "type": "text",
                                        "text": {"body": body_text},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }

    def test_text_message_flattened(self):
        flat = flatten_messages(self._meta_payload("hello bot"))
        assert len(flat) == 1
        msg = flat[0]
        assert msg["platform"] == "whatsapp"
        assert msg["from"] == "15551234567"
        assert msg["chat_id"] == "15551234567"
        assert msg["body"] == "hello bot"
        assert msg["id"] == "wamid.ABC"

    def test_non_text_message_has_empty_body(self):
        payload = self._meta_payload("ignored")
        payload["entry"][0]["changes"][0]["value"]["messages"][0]["type"] = "image"
        flat = flatten_messages(payload)
        assert flat[0]["body"] == ""
        assert flat[0]["message_type"] == "image"

    def test_empty_envelope_yields_no_messages(self):
        assert flatten_messages({"entry": []}) == []
        assert flatten_messages({}) == []


class TestGatewayNormalization:
    """The flattened message normalizes through the gateway WhatsAppAdapter."""

    @pytest.mark.asyncio
    async def test_flattened_message_normalizes(self):
        from services.gateway.gateway_manager import GatewayManager

        gateway = GatewayManager()
        raw = {
            "platform": "whatsapp",
            "from": "15551234567",
            "chat_id": "15551234567",
            "body": "hi",
            "id": "wamid.X",
            "timestamp": "1700000000",
            "message_type": "text",
        }
        unified = await gateway.normalize_message(raw)
        assert unified.platform == "whatsapp"
        assert unified.user_id == "15551234567"
        assert unified.message == "hi"


class TestRoundTripSignatureOverRealPayload:
    """End-to-end: a signed Meta payload verifies and flattens to one message."""

    def test_signed_payload_verifies_and_flattens(self):
        secret = "app-secret"  # nosec B105 - test fixture
        payload = {
            "entry": [
                {"changes": [{"value": {"messages": [{"from": "1", "id": "m", "type": "text", "text": {"body": "yo"}}]}}]}
            ]
        }
        raw = json.dumps(payload).encode("utf-8")
        sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        assert verify_webhook_signature(raw, sig, secret) is True
        flat = flatten_messages(json.loads(raw.decode("utf-8")))
        assert len(flat) == 1 and flat[0]["body"] == "yo"
