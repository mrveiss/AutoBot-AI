# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Web Platform Adapter for Message Gateway"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

from .base_adapter import BaseAdapter, GatewayMessage, NormalizedResponse

logger = get_logger(__name__)


class WebAdapter(BaseAdapter):
    """Web platform adapter for unified message gateway."""

    def __init__(self) -> None:
        super().__init__("web")

    async def normalize_message(self, raw_message: Dict[str, Any]) -> GatewayMessage:
        """Convert web message to unified schema."""
        metadata = await self.extract_metadata(raw_message)
        metadata["session_id"] = raw_message.get("session_id")
        metadata["user_agent"] = raw_message.get("user_agent")

        return GatewayMessage(
            user_id=raw_message["user_id"],
            platform="web",
            channel_id=raw_message.get("channel_id", "default"),
            message=raw_message["message"],
            timestamp=float(raw_message.get("timestamp", 0)),
            metadata=metadata,
        )

    async def denormalize_response(self, unified_response: NormalizedResponse) -> Dict[str, Any]:
        """Convert unified response to web format."""
        web_response = {
            "user_id": unified_response.user_id,
            "channel_id": unified_response.channel_id,
            "message": unified_response.content,
            "response_type": unified_response.response_type,
        }

        return web_response

    def get_rate_limit(self) -> Dict[str, int]:
        """Web rate limit: 100 requests/second with burst of 200."""
        return {"requests_per_second": 100, "burst_size": 200}
