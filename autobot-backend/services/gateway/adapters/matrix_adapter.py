# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Matrix Platform Adapter for Message Gateway

Uses matrix-nio client library.  E2EE is supported when the homeserver has
encryption enabled; set AUTOBOT_MATRIX_E2EE=true to opt in.  The adapter
normalizes m.room.message events; other event types are silently skipped.
"""

import os
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

from .base_adapter import BaseAdapter, GatewayMessage, NormalizedResponse

logger = get_logger(__name__)

MATRIX_E2EE_ENABLED = os.getenv("AUTOBOT_MATRIX_E2EE", "false").lower() == "true"


class MatrixAdapter(BaseAdapter):
    """Matrix adapter for self-hosted and federated homeservers.

    Handles m.room.message events from matrix-nio sync callbacks.
    E2EE is transparent when AUTOBOT_MATRIX_E2EE=true — matrix-nio decrypts
    before calling normalize_message so this adapter always receives plaintext.
    """

    def __init__(self) -> None:
        super().__init__("matrix")
        self._e2ee = MATRIX_E2EE_ENABLED

    async def normalize_message(self, raw_message: Dict[str, Any]) -> GatewayMessage:
        """Convert matrix-nio RoomMessage event dict to unified schema."""
        metadata = await self.extract_metadata(raw_message)

        event_id = raw_message.get("event_id", "")
        sender = raw_message.get("sender", "")
        room_id = raw_message.get("room_id", "")
        content = raw_message.get("content", {})
        relates_to = content.get("m.relates_to", {})

        metadata["event_id"] = event_id
        metadata["msgtype"] = content.get("msgtype", "m.text")
        metadata["relates_to"] = relates_to
        metadata["e2ee"] = self._e2ee
        metadata["thread_id"] = relates_to.get("event_id") if relates_to.get("rel_type") == "m.thread" else None
        metadata["reply_to"] = (
            relates_to.get("m.in_reply_to", {}).get("event_id") if relates_to.get("rel_type") != "m.thread" else None
        )

        return GatewayMessage(
            user_id=sender,
            platform="matrix",
            channel_id=room_id,
            message=content.get("body", ""),
            timestamp=float(raw_message.get("origin_server_ts", 0)) / 1000,
            metadata=metadata,
        )

    async def denormalize_response(self, unified_response: NormalizedResponse) -> Dict[str, Any]:
        """Convert unified response to matrix-nio send_message payload."""
        content: Dict[str, Any] = {
            "msgtype": "m.text",
            "body": unified_response.content,
        }

        thread_id = unified_response.metadata.get("thread_id")
        if thread_id:
            content["m.relates_to"] = {
                "rel_type": "m.thread",
                "event_id": thread_id,
            }
        elif unified_response.response_type == "thread_reply":
            reply_event = unified_response.metadata.get("event_id")
            if reply_event:
                content["m.relates_to"] = {
                    "m.in_reply_to": {"event_id": reply_event},
                }

        return {
            "room_id": unified_response.channel_id,
            "content": content,
        }

    def get_rate_limit(self) -> Dict[str, int]:
        """Matrix: homeserver-enforced, but ~10 req/s is safe for most instances."""
        return {"requests_per_second": 10, "burst_size": 20}
