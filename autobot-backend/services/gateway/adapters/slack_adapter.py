# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Slack Platform Adapter for Message Gateway"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

from .base_adapter import BaseAdapter, GatewayMessage, NormalizedResponse

logger = get_logger(__name__)


class SlackAdapter(BaseAdapter):
    """Slack platform adapter for unified message gateway."""

    def __init__(self) -> None:
        super().__init__("slack")

    async def normalize_message(self, raw_message: Dict[str, Any]) -> GatewayMessage:
        """Convert Slack message to unified schema."""
        metadata = await self.extract_metadata(raw_message)
        # Slack's "ts" doubles as the message's unique id within a channel; fall
        # back to it (then to "timestamp", which every raw payload already
        # carries) when the caller doesn't supply an explicit "message_id" (#14028).
        message_id = str(raw_message.get("message_id") or raw_message.get("ts") or raw_message.get("timestamp") or "")
        metadata["message_id"] = message_id
        metadata["thread_ts"] = raw_message.get("thread_ts")
        metadata["is_thread_reply"] = bool(raw_message.get("thread_ts"))

        return GatewayMessage(
            user_id=raw_message["user_id"],
            platform="slack",
            channel_id=raw_message["channel_id"],
            message=raw_message["text"],
            timestamp=float(raw_message.get("timestamp", 0)),
            metadata=metadata,
            message_id=message_id,
        )

    async def denormalize_response(self, unified_response: NormalizedResponse) -> Dict[str, Any]:
        """Convert unified response to Slack format."""
        slack_response = {
            "channel": unified_response.channel_id,
            "text": unified_response.content,
            "user": unified_response.user_id,
        }

        # Thread replies in Slack use thread_ts
        if unified_response.response_type == "thread_reply":
            slack_response["thread_ts"] = unified_response.metadata.get("thread_ts")

        return slack_response

    def get_rate_limit(self) -> Dict[str, int]:
        """Slack rate limit: 1 request/second with burst of 10."""
        return {"requests_per_second": 1, "burst_size": 10}
