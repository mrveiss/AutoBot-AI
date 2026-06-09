# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Signal Platform Adapter for Message Gateway

Requires AUTOBOT_SIGNAL_ENABLED=true and a running signal-cli daemon (or
semaphore REST bridge) reachable at AUTOBOT_SIGNAL_CLI_URL.  When the env
flag is absent this adapter is registered but silently no-ops outbound sends
so existing gateway tests are unaffected.
"""

import os
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

from .base_adapter import BaseAdapter, NormalizedResponse, UnifiedMessage

logger = get_logger(__name__)

SIGNAL_ENABLED = os.getenv("AUTOBOT_SIGNAL_ENABLED", "false").lower() == "true"


class SignalAdapter(BaseAdapter):
    """Signal adapter bridging via signal-cli daemon or semaphore REST API.

    E2EE is preserved end-to-end — the daemon handles key management and
    encryption; this adapter only marshals plaintext after decryption has
    already happened locally.
    """

    def __init__(self) -> None:
        super().__init__("signal")
        self._enabled = SIGNAL_ENABLED
        if not self._enabled:
            logger.info("SignalAdapter loaded but AUTOBOT_SIGNAL_ENABLED is not set — outbound sends disabled")

    async def normalize_message(self, raw_message: Dict[str, Any]) -> UnifiedMessage:
        """Convert signal-cli envelope/semaphore webhook to unified schema."""
        metadata = await self.extract_metadata(raw_message)

        envelope = raw_message.get("envelope") or raw_message
        data_message = envelope.get("dataMessage") or {}
        source = envelope.get("source", "")
        group_info = data_message.get("groupInfo") or {}

        metadata["message_id"] = data_message.get("timestamp")
        metadata["group_id"] = group_info.get("groupId")
        metadata["is_group"] = bool(group_info)
        metadata["quote"] = data_message.get("quote")
        metadata["e2ee"] = True

        channel_id = group_info.get("groupId") or source

        return UnifiedMessage(
            user_id=source,
            platform="signal",
            channel_id=channel_id,
            message=data_message.get("message", ""),
            timestamp=float(data_message.get("timestamp", 0)) / 1000,
            metadata=metadata,
        )

    async def denormalize_response(self, unified_response: NormalizedResponse) -> Dict[str, Any]:
        """Convert unified response to signal-cli send payload.

        Returns a no-op payload when AUTOBOT_SIGNAL_ENABLED is false so the
        gateway can still call this path safely in tests.
        """
        if not self._enabled:
            return {"_signal_disabled": True, "content": unified_response.content}

        payload: Dict[str, Any] = {
            "recipient": unified_response.channel_id,
            "message": unified_response.content,
        }

        group_id = unified_response.metadata.get("group_id")
        if group_id:
            payload["group_id"] = group_id
            payload.pop("recipient", None)

        return payload

    def get_rate_limit(self) -> Dict[str, int]:
        """Signal rate limit: conservative 1 req/s to respect E2EE transport limits."""
        return {"requests_per_second": 1, "burst_size": 5}
