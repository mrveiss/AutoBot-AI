# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Discord Platform Adapter for Message Gateway"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

from .base_adapter import BaseAdapter, NormalizedResponse, UnifiedMessage

logger = get_logger(__name__)


class DiscordAdapter(BaseAdapter):
    """Discord platform adapter for unified message gateway."""

    def __init__(self) -> None:
        super().__init__("discord")

    async def normalize_message(self, raw_message: Dict[str, Any]) -> UnifiedMessage:
        """Convert Discord message to unified schema."""
        metadata = await self.extract_metadata(raw_message)
        metadata["message_id"] = raw_message.get("id")
        metadata["referenced_message"] = raw_message.get("referenced_message")

        return UnifiedMessage(
            user_id=raw_message["author"]["id"],
            platform="discord",
            channel_id=raw_message["channel_id"],
            message=raw_message["content"],
            timestamp=float(raw_message.get("timestamp", 0)),
            metadata=metadata,
        )

    async def denormalize_response(self, unified_response: NormalizedResponse) -> Dict[str, Any]:
        """Convert unified response to Discord format."""
        discord_response = {
            "channel_id": unified_response.channel_id,
            "content": unified_response.content,
        }

        # Discord thread replies reference the message
        if unified_response.response_type == "thread_reply":
            discord_response["message_reference"] = {"message_id": unified_response.metadata.get("message_id")}

        return discord_response

    def get_rate_limit(self) -> Dict[str, int]:
        """Discord rate limit: 10 requests/second with burst of 50."""
        return {"requests_per_second": 10, "burst_size": 50}
