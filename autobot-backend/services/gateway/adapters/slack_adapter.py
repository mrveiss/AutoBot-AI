# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Slack Platform Adapter for Message Gateway"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

from .base_adapter import BaseAdapter, NormalizedResponse, UnifiedMessage

logger = get_logger(__name__)


class SlackAdapter(BaseAdapter):
    """Slack platform adapter for unified message gateway."""

    def __init__(self) -> None:
        super().__init__("slack")

    async def normalize_message(self, raw_message: Dict[str, Any]) -> UnifiedMessage:
        """Convert Slack message to unified schema."""
        metadata = await self.extract_metadata(raw_message)
        metadata["thread_ts"] = raw_message.get("thread_ts")
        metadata["is_thread_reply"] = bool(raw_message.get("thread_ts"))

        return UnifiedMessage(
            user_id=raw_message["user_id"],
            platform="slack",
            channel_id=raw_message["channel_id"],
            message=raw_message["text"],
            timestamp=float(raw_message.get("timestamp", 0)),
            metadata=metadata,
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
