# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""WhatsApp Platform Adapter for Message Gateway"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

from .base_adapter import BaseAdapter, GatewayMessage, NormalizedResponse

logger = get_logger(__name__)


class WhatsAppAdapter(BaseAdapter):
    """WhatsApp platform adapter for unified message gateway."""

    def __init__(self) -> None:
        super().__init__("whatsapp")

    async def normalize_message(self, raw_message: Dict[str, Any]) -> GatewayMessage:
        """Convert WhatsApp message to unified schema."""
        metadata = await self.extract_metadata(raw_message)
        metadata["message_id"] = raw_message.get("id")
        metadata["is_group"] = raw_message.get("is_group", False)
        # Carry the message type (and media reference) so downstream routing can
        # label/handle attachments — flatten_messages records these but the base
        # extract_metadata does not propagate them (GH#10481).
        metadata["message_type"] = raw_message.get("message_type", "text")
        if raw_message.get("media_id"):
            metadata["media_id"] = raw_message["media_id"]

        return GatewayMessage(
            user_id=raw_message["from"],
            platform="whatsapp",
            channel_id=raw_message["chat_id"],
            message=raw_message["body"],
            timestamp=float(raw_message.get("timestamp", 0)),
            metadata=metadata,
        )

    async def denormalize_response(self, unified_response: NormalizedResponse) -> Dict[str, Any]:
        """Convert unified response to WhatsApp format."""
        whatsapp_response = {
            "to": unified_response.channel_id,
            "body": unified_response.content,
        }

        # WhatsApp reply type
        if unified_response.response_type == "reply":
            whatsapp_response["reply_to"] = unified_response.metadata.get("message_id")

        return whatsapp_response

    def get_rate_limit(self) -> Dict[str, int]:
        """WhatsApp rate limit: 80 requests/second with burst of 100."""
        return {"requests_per_second": 80, "burst_size": 100}
