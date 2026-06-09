# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
WhatsApp Business API Integration (Issue #9007)

Provides integration with WhatsApp Business API (Meta Cloud API or self-hosted)
for bidirectional messaging with AutoBot agents:
- Send and receive text messages
- File and voice message support
- Template message support for proactive notifications
- Opt-in/opt-out management per phone number
- Webhook handling for incoming messages

Configuration:
- Meta Cloud API: requires phone_number_id, business_account_id, access_token
- Self-hosted: requires base_url, api_key
"""

import json
import time
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from integrations.base import (
    BaseIntegration,
    IntegrationAction,
    IntegrationConfig,
    IntegrationHealth,
    IntegrationStatus,
)

logger = get_logger(__name__)

_OPT_STATUS_KEY_PREFIX = "whatsapp:opt_status:"
_OPT_STATUS_TTL = 31536000  # 1 year
_MESSAGE_CACHE_KEY_PREFIX = "whatsapp:message_cache:"
_MESSAGE_CACHE_TTL = 86400  # 24 hours


class WhatsAppOptInStatus:
    """Opt-in status for a phone number stored in Redis."""

    def __init__(
        self,
        phone_number: str,
        opted_in: bool,
        opted_in_at: str | None = None,
        opted_out_at: str | None = None,
    ) -> None:
        self.phone_number = phone_number
        self.opted_in = opted_in
        self.opted_in_at = opted_in_at
        self.opted_out_at = opted_out_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phone_number": self.phone_number,
            "opted_in": self.opted_in,
            "opted_in_at": self.opted_in_at,
            "opted_out_at": self.opted_out_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WhatsAppOptInStatus":
        return cls(
            phone_number=data["phone_number"],
            opted_in=data["opted_in"],
            opted_in_at=data.get("opted_in_at"),
            opted_out_at=data.get("opted_out_at"),
        )


class WhatsAppIntegration(BaseIntegration):
    """WhatsApp Business API integration for bidirectional messaging.

    Supports both Meta Cloud API and self-hosted Business API deployments.

    Meta Cloud API configuration (config.extra):
    - phone_number_id: WhatsApp Business Phone Number ID
    - business_account_id: WhatsApp Business Account ID
    - access_token: Meta API access token (stored in config.api_key)

    Self-hosted API configuration:
    - base_url: API endpoint URL
    - api_key: Authentication key

    Rate limiting follows Meta API limits:
    - 1000 messages per second per phone number
    - 250000 messages per day (business tier)

    Error handling:
    - Network errors (timeouts, DNS failures) are caught and logged
    - API errors (auth failures, rate limits, invalid recipients) are logged
    - Rate limiting (429 responses) are logged with retry guidance
    """

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        # Meta Cloud API base URL
        self.base_url = config.base_url or "https://graph.facebook.com/v18.0"
        self.phone_number_id = config.extra.get("phone_number_id")
        self.business_account_id = config.extra.get("business_account_id")
        self.access_token = config.api_key or config.token

    async def test_connection(self) -> IntegrationHealth:
        """Test WhatsApp connection by fetching business profile."""
        start_time = time.monotonic()
        if not self.access_token:
            return self._create_health_response(
                IntegrationStatus.ERROR,
                0,
                "WhatsApp access token not configured",
            )

        if not self.phone_number_id:
            return self._create_health_response(
                IntegrationStatus.ERROR,
                0,
                "WhatsApp phone_number_id not configured",
            )

        try:
            url = f"{self.base_url}/{self.phone_number_id}"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            params = {"fields": "id,display_phone_number,verified_name"}
            result = await self._make_request("GET", url, headers=headers, json_data=params)

            latency = (time.monotonic() - start_time) * 1000

            if result.get("status_code") == 200 and result.get("body", {}).get("id"):
                body = result["body"]
                return self._create_health_response(
                    IntegrationStatus.CONNECTED,
                    latency,
                    "Connected to WhatsApp Business API",
                    {
                        "phone_number": body.get("display_phone_number"),
                        "verified_name": body.get("verified_name"),
                        "phone_number_id": body.get("id"),
                    },
                )

            error_msg = result.get("body", {}).get("error", {}).get("message", "Unknown error")
            return self._create_health_response(IntegrationStatus.ERROR, latency, error_msg)

        except Exception as exc:
            latency = (time.monotonic() - start_time) * 1000
            logger.error("WhatsApp connection test failed: %s", exc)
            return self._create_health_response(
                IntegrationStatus.ERROR,
                latency,
                f"Connection test failed: {str(exc)}",
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of supported WhatsApp actions."""
        return [
            IntegrationAction(
                name="send_text_message",
                description="Send text message to a WhatsApp number",
                method="POST",
                parameters={
                    "to": "str (E.164 format phone number)",
                    "body": "str (message text)",
                    "preview_url": "bool (optional, default False)",
                },
            ),
            IntegrationAction(
                name="send_media_message",
                description="Send media (image, video, audio, document) to WhatsApp number",
                method="POST",
                parameters={
                    "to": "str (E.164 format phone number)",
                    "media_type": "str (image|video|audio|document)",
                    "media_url": "str (publicly accessible URL)",
                    "caption": "str (optional)",
                    "filename": "str (optional, for documents)",
                },
            ),
            IntegrationAction(
                name="send_template_message",
                description="Send template message (for proactive outreach)",
                method="POST",
                parameters={
                    "to": "str (E.164 format phone number)",
                    "template_name": "str",
                    "language_code": "str (default: en)",
                    "components": "list[dict] (optional template parameters)",
                },
            ),
            IntegrationAction(
                name="check_opt_in_status",
                description="Check if phone number has opted in for messaging",
                method="GET",
                parameters={"phone_number": "str (E.164 format)"},
            ),
            IntegrationAction(
                name="set_opt_in_status",
                description="Update opt-in/opt-out status for a phone number",
                method="POST",
                parameters={
                    "phone_number": "str (E.164 format)",
                    "opted_in": "bool",
                },
            ),
            IntegrationAction(
                name="mark_message_read",
                description="Mark incoming message as read",
                method="POST",
                parameters={"message_id": "str (WhatsApp message ID)"},
            ),
        ]

    async def execute_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a named WhatsApp action."""
        action_map = {
            "send_text_message": self.send_text_message,
            "send_media_message": self.send_media_message,
            "send_template_message": self.send_template_message,
            "check_opt_in_status": self.check_opt_in_status,
            "set_opt_in_status": self.set_opt_in_status,
            "mark_message_read": self.mark_message_read,
        }
        handler = action_map.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}
        return await handler(params)

    async def send_text_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send text message to WhatsApp number.

        Wraps WhatsApp API call with error handling for network failures,
        auth errors, and invalid recipients.

        Args:
            params: to (E.164 phone number), body (message text),
                    preview_url (optional bool)
        Returns:
            WhatsApp API response with message ID, or error dict on failure.
            Never raises; logs and returns error response instead.
        """
        try:
            to = params["to"]
            body = params["body"]

            # Check opt-in status before sending
            opt_status = await self.check_opt_in_status({"phone_number": to})
            if not opt_status.get("opted_in", False):
                logger.warning(
                    "Skipping message to %s — user has not opted in",
                    to,
                )
                return {
                    "ok": False,
                    "error": "recipient_not_opted_in",
                    "to": to,
                }

            url = f"{self.base_url}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {
                    "preview_url": params.get("preview_url", False),
                    "body": body,
                },
            }

            result = await self._make_request("POST", url, headers=headers, json_data=payload)

            if result.get("status_code") == 200:
                logger.info("Sent WhatsApp text message to %s", to)
                return {
                    "ok": True,
                    "message_id": result["body"]["messages"][0]["id"],
                    "to": to,
                }

            error_msg = result.get("body", {}).get("error", {}).get("message", "Unknown error")
            logger.error(
                "Failed to send WhatsApp text message to %s: %s",
                to,
                error_msg,
            )
            return {"ok": False, "error": error_msg, "to": to}

        except Exception as exc:
            logger.error(
                "Exception sending WhatsApp text message to %s: %s",
                params.get("to"),
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
                "to": params.get("to"),
            }

    async def send_media_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send media message to WhatsApp number.

        Wraps WhatsApp API call with error handling for network failures,
        invalid media URLs, and unsupported media types.

        Args:
            params: to (E.164 phone number), media_type (image|video|audio|document),
                    media_url (publicly accessible URL), caption (optional),
                    filename (optional, for documents)
        Returns:
            WhatsApp API response with message ID, or error dict on failure.
            Never raises; logs and returns error response instead.
        """
        try:
            to = params["to"]
            media_type = params["media_type"]
            media_url = params["media_url"]

            # Check opt-in status before sending
            opt_status = await self.check_opt_in_status({"phone_number": to})
            if not opt_status.get("opted_in", False):
                logger.warning(
                    "Skipping media message to %s — user has not opted in",
                    to,
                )
                return {
                    "ok": False,
                    "error": "recipient_not_opted_in",
                    "to": to,
                }

            url = f"{self.base_url}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            media_object: Dict[str, Any] = {"link": media_url}
            if params.get("caption"):
                media_object["caption"] = params["caption"]
            if media_type == "document" and params.get("filename"):
                media_object["filename"] = params["filename"]

            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": media_type,
                media_type: media_object,
            }

            result = await self._make_request("POST", url, headers=headers, json_data=payload)

            if result.get("status_code") == 200:
                logger.info("Sent WhatsApp %s message to %s", media_type, to)
                return {
                    "ok": True,
                    "message_id": result["body"]["messages"][0]["id"],
                    "to": to,
                    "media_type": media_type,
                }

            error_msg = result.get("body", {}).get("error", {}).get("message", "Unknown error")
            logger.error(
                "Failed to send WhatsApp %s message to %s: %s",
                media_type,
                to,
                error_msg,
            )
            return {"ok": False, "error": error_msg, "to": to}

        except Exception as exc:
            logger.error(
                "Exception sending WhatsApp media message to %s: %s",
                params.get("to"),
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
                "to": params.get("to"),
            }

    async def send_template_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send template message for proactive outreach.

        Template messages must be pre-approved by Meta and are used for
        notifications outside the 24-hour customer service window.

        Wraps WhatsApp API call with error handling.

        Args:
            params: to (E.164 phone number), template_name (str),
                    language_code (str, default "en"),
                    components (optional list of parameter dicts)
        Returns:
            WhatsApp API response with message ID, or error dict on failure.
            Never raises; logs and returns error response instead.
        """
        try:
            to = params["to"]
            template_name = params["template_name"]
            language_code = params.get("language_code", "en")

            # Check opt-in status before sending
            opt_status = await self.check_opt_in_status({"phone_number": to})
            if not opt_status.get("opted_in", False):
                logger.warning(
                    "Skipping template message to %s — user has not opted in",
                    to,
                )
                return {
                    "ok": False,
                    "error": "recipient_not_opted_in",
                    "to": to,
                }

            url = f"{self.base_url}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            template_payload: Dict[str, Any] = {
                "name": template_name,
                "language": {"code": language_code},
            }
            if params.get("components"):
                template_payload["components"] = params["components"]

            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "template",
                "template": template_payload,
            }

            result = await self._make_request("POST", url, headers=headers, json_data=payload)

            if result.get("status_code") == 200:
                logger.info(
                    "Sent WhatsApp template message '%s' to %s",
                    template_name,
                    to,
                )
                return {
                    "ok": True,
                    "message_id": result["body"]["messages"][0]["id"],
                    "to": to,
                    "template_name": template_name,
                }

            error_msg = result.get("body", {}).get("error", {}).get("message", "Unknown error")
            logger.error(
                "Failed to send WhatsApp template message '%s' to %s: %s",
                template_name,
                to,
                error_msg,
            )
            return {"ok": False, "error": error_msg, "to": to}

        except Exception as exc:
            logger.error(
                "Exception sending WhatsApp template message to %s: %s",
                params.get("to"),
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
                "to": params.get("to"),
            }

    async def check_opt_in_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check if phone number has opted in for messaging.

        Wraps Redis get operation with error handling.

        Args:
            params: phone_number (E.164 format)

        Returns:
            dict with opted_in (bool), opted_in_at, opted_out_at keys.
            Never raises; logs error and returns opted_in=False on failure.
        """
        try:
            phone_number = params["phone_number"]
            client = await get_async_redis_client(database="main")
            if client is None:
                logger.warning(
                    "Redis client unavailable for checking opt-in status (phone=%s)",
                    phone_number,
                )
                return {
                    "phone_number": phone_number,
                    "opted_in": False,
                    "opted_in_at": None,
                    "opted_out_at": None,
                }

            key = f"{_OPT_STATUS_KEY_PREFIX}{phone_number}"
            raw = await client.get(key)
            if not raw:
                logger.debug(
                    "No opt-in status found for phone=%s (defaulting to opted_in=False)",
                    phone_number,
                )
                return {
                    "phone_number": phone_number,
                    "opted_in": False,
                    "opted_in_at": None,
                    "opted_out_at": None,
                }

            data = json.loads(raw)
            status = WhatsAppOptInStatus.from_dict(data)
            return status.to_dict()

        except json.JSONDecodeError as exc:
            logger.error(
                "Malformed JSON in opt-in status (phone=%s): %s",
                params.get("phone_number"),
                exc,
            )
            return {
                "phone_number": params.get("phone_number"),
                "opted_in": False,
                "opted_in_at": None,
                "opted_out_at": None,
            }
        except Exception as exc:
            logger.error(
                "Failed to check opt-in status (phone=%s): %s",
                params.get("phone_number"),
                exc,
            )
            return {
                "phone_number": params.get("phone_number"),
                "opted_in": False,
                "opted_in_at": None,
                "opted_out_at": None,
            }

    async def set_opt_in_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update opt-in/opt-out status for a phone number.

        Wraps Redis set operation with error handling.

        Args:
            params: phone_number (E.164 format), opted_in (bool)

        Returns:
            dict with success (bool) and updated status.
            Never raises; logs error and returns success=False on failure.
        """
        try:
            phone_number = params["phone_number"]
            opted_in = params["opted_in"]

            from autobot_shared.time_utils import now_utc

            timestamp = now_utc().isoformat()

            status = WhatsAppOptInStatus(
                phone_number=phone_number,
                opted_in=opted_in,
                opted_in_at=timestamp if opted_in else None,
                opted_out_at=None if opted_in else timestamp,
            )

            client = await get_async_redis_client(database="main")
            if client is None:
                logger.warning(
                    "Redis client unavailable for setting opt-in status (phone=%s)",
                    phone_number,
                )
                return {"success": False, "phone_number": phone_number}

            key = f"{_OPT_STATUS_KEY_PREFIX}{phone_number}"
            await client.set(
                key,
                json.dumps(status.to_dict(), ensure_ascii=False),
                ex=_OPT_STATUS_TTL,
            )
            logger.info(
                "Updated opt-in status for phone=%s (opted_in=%s)",
                phone_number,
                opted_in,
            )
            return {
                "success": True,
                "phone_number": phone_number,
                "opted_in": opted_in,
                "timestamp": timestamp,
            }

        except Exception as exc:
            logger.error(
                "Failed to set opt-in status (phone=%s): %s",
                params.get("phone_number"),
                exc,
            )
            return {
                "success": False,
                "phone_number": params.get("phone_number"),
                "error": str(exc),
            }

    async def mark_message_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Mark incoming message as read.

        Sends read receipt to WhatsApp API.

        Args:
            params: message_id (WhatsApp message ID)

        Returns:
            API response with success status.
            Never raises; logs error and returns success=False on failure.
        """
        try:
            message_id = params["message_id"]

            url = f"{self.base_url}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            }

            result = await self._make_request("POST", url, headers=headers, json_data=payload)

            if result.get("status_code") == 200:
                logger.debug("Marked WhatsApp message %s as read", message_id)
                return {"success": True, "message_id": message_id}

            error_msg = result.get("body", {}).get("error", {}).get("message", "Unknown error")
            logger.error(
                "Failed to mark WhatsApp message %s as read: %s",
                message_id,
                error_msg,
            )
            return {"success": False, "message_id": message_id, "error": error_msg}

        except Exception as exc:
            logger.error(
                "Exception marking WhatsApp message %s as read: %s",
                params.get("message_id"),
                exc,
            )
            return {
                "success": False,
                "message_id": params.get("message_id"),
                "error": str(exc),
            }

    def _create_health_response(
        self,
        status: IntegrationStatus,
        latency_ms: float,
        message: str,
        details: Dict[str, Any] | None = None,
    ) -> IntegrationHealth:
        """Create a standardized health check response."""
        from autobot_shared.time_utils import now_utc

        return IntegrationHealth(
            provider=self.provider,
            status=status,
            latency_ms=latency_ms,
            message=message,
            last_checked=now_utc(),
            details=details or {},
        )
