# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Telegram Platform Adapter for Message Gateway"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

from .base_adapter import BaseAdapter, NormalizedResponse, UnifiedMessage

logger = get_logger(__name__)


class TelegramAdapter(BaseAdapter):
    """Telegram platform adapter using python-telegram-bot Bot API."""

    def __init__(self) -> None:
        super().__init__("telegram")

    async def normalize_message(self, raw_message: Dict[str, Any]) -> UnifiedMessage:
        """Convert Telegram Update/Message object to unified schema."""
        message = raw_message.get("message") or raw_message
        metadata = await self.extract_metadata(raw_message)

        chat = message.get("chat", {})
        from_user = message.get("from", {})
        reply_to = message.get("reply_to_message")

        metadata["message_id"] = message.get("message_id")
        metadata["chat_type"] = chat.get("type", "private")
        metadata["reply_to_message_id"] = reply_to.get("message_id") if reply_to else None
        metadata["is_reply"] = reply_to is not None
        metadata["thread_id"] = message.get("message_thread_id")

        return UnifiedMessage(
            user_id=str(from_user.get("id", "")),
            platform="telegram",
            channel_id=str(chat.get("id", "")),
            message=message.get("text", ""),
            timestamp=float(message.get("date", 0)),
            metadata=metadata,
        )

    async def denormalize_response(self, unified_response: NormalizedResponse) -> Dict[str, Any]:
        """Convert unified response to Telegram sendMessage payload."""
        payload: Dict[str, Any] = {
            "chat_id": unified_response.channel_id,
            "text": unified_response.content,
            "parse_mode": "Markdown",
        }

        if unified_response.response_type == "thread_reply":
            reply_id = unified_response.metadata.get("message_id")
            if reply_id:
                payload["reply_to_message_id"] = reply_id

        thread_id = unified_response.metadata.get("thread_id")
        if thread_id:
            payload["message_thread_id"] = thread_id

        return payload

    def get_rate_limit(self) -> Dict[str, int]:
        """Telegram Bot API: 30 messages/second globally, 1/second per chat."""
        return {"requests_per_second": 30, "burst_size": 30}
