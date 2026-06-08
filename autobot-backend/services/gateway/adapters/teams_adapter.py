# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Microsoft Teams Platform Adapter for Message Gateway"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

from .base_adapter import BaseAdapter, NormalizedResponse, UnifiedMessage

logger = get_logger(__name__)


class TeamsAdapter(BaseAdapter):
    """Microsoft Teams platform adapter for unified message gateway."""

    def __init__(self) -> None:
        super().__init__("teams")

    async def normalize_message(self, raw_message: Dict[str, Any]) -> UnifiedMessage:
        """Convert Teams message to unified schema."""
        metadata = await self.extract_metadata(raw_message)
        metadata["message_id"] = raw_message.get("id")
        metadata["reply_to_id"] = raw_message.get("replyToId")

        return UnifiedMessage(
            user_id=raw_message["from"]["id"],
            platform="teams",
            channel_id=raw_message["channelData"]["channel"]["id"],
            message=raw_message["text"],
            timestamp=float(raw_message.get("timestamp", 0)),
            metadata=metadata,
        )

    async def denormalize_response(self, unified_response: NormalizedResponse) -> Dict[str, Any]:
        """Convert unified response to Teams format."""
        teams_response = {
            "type": "message",
            "from": {"id": unified_response.user_id},
            "text": unified_response.content,
            "channelData": {"channel": {"id": unified_response.channel_id}},
        }

        # Teams reply type
        if unified_response.response_type == "reply":
            teams_response["replyToId"] = unified_response.metadata.get("message_id")

        return teams_response

    def get_rate_limit(self) -> Dict[str, int]:
        """Teams rate limit: 50 requests/second with burst of 100."""
        return {"requests_per_second": 50, "burst_size": 100}
