# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""iMessage Platform Adapter for Message Gateway

macOS-only.  Requires AUTOBOT_IMESSAGE_ENABLED=true and a macOS host with
Messages.app.  Sends via osascript AppleScript bridge.  On non-macOS hosts
the adapter loads but outbound sends are disabled; messages can still be
normalized (inbound webhook from a macOS relay).
"""

import os
import platform
import sys
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

from .base_adapter import BaseAdapter, NormalizedResponse, UnifiedMessage

logger = get_logger(__name__)

IMESSAGE_ENABLED = os.getenv("AUTOBOT_IMESSAGE_ENABLED", "false").lower() == "true"
_IS_MACOS = sys.platform == "darwin" or platform.system() == "Darwin"


class IMessageAdapter(BaseAdapter):
    """iMessage adapter via AppleScript/osascript bridge.

    Sends are only available on macOS with Messages.app.  The adapter
    normalizes inbound webhooks from an OpenClaw-style macOS relay on any
    platform, but outbound denormalization is a no-op unless both
    AUTOBOT_IMESSAGE_ENABLED=true and the host is macOS.
    """

    def __init__(self) -> None:
        super().__init__("imessage")
        self._send_enabled = IMESSAGE_ENABLED and _IS_MACOS
        if IMESSAGE_ENABLED and not _IS_MACOS:
            logger.warning("AUTOBOT_IMESSAGE_ENABLED=true but host is not macOS — outbound sends disabled")
        elif not IMESSAGE_ENABLED:
            logger.info("IMessageAdapter loaded; set AUTOBOT_IMESSAGE_ENABLED=true on a macOS host to enable sends")

    async def normalize_message(self, raw_message: Dict[str, Any]) -> UnifiedMessage:
        """Convert macOS relay webhook payload to unified schema."""
        metadata = await self.extract_metadata(raw_message)

        metadata["message_id"] = raw_message.get("id") or raw_message.get("guid")
        metadata["is_group"] = raw_message.get("is_group", False)
        metadata["service"] = raw_message.get("service", "iMessage")
        metadata["macos_only"] = True

        sender = raw_message.get("sender") or raw_message.get("from", "")
        chat_id = raw_message.get("chat_id") or raw_message.get("room_name") or sender

        return UnifiedMessage(
            user_id=sender,
            platform="imessage",
            channel_id=chat_id,
            message=raw_message.get("text") or raw_message.get("body", ""),
            timestamp=float(raw_message.get("timestamp", 0)),
            metadata=metadata,
        )

    async def denormalize_response(self, unified_response: NormalizedResponse) -> Dict[str, Any]:
        """Convert unified response to osascript send payload.

        Returns a no-op dict when not running on macOS with the feature enabled.
        """
        if not self._send_enabled:
            return {
                "_imessage_disabled": True,
                "_reason": "requires macOS + AUTOBOT_IMESSAGE_ENABLED=true",
                "content": unified_response.content,
            }

        return {
            "recipient": unified_response.channel_id,
            "message": unified_response.content,
            "service": unified_response.metadata.get("service", "iMessage"),
        }

    def get_rate_limit(self) -> Dict[str, int]:
        """iMessage: AppleScript bridge is slow; cap at 1 req/s."""
        return {"requests_per_second": 1, "burst_size": 3}
