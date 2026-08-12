# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Base Message Adapter for Platform Gateway

Defines the abstract interface for platform-specific message adapters.
All platform adapters (Slack, Discord, WhatsApp, Teams, Web) inherit from this.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


@dataclass
class GatewayMessage:
    """Raw inbound platform payload normalized from all platform adapters.

    ``message_id`` is mandatory (#14028): the ingest governance stage in
    ``GatewayManager.normalize_message`` dedups on
    ``(platform, channel_id, message_id)`` and rejects any message where the
    adapter could not resolve one, fail-closed, rather than routing it with
    the field silently absent.
    """

    user_id: str
    platform: str  # 'web', 'slack', 'discord', 'whatsapp', 'teams'
    channel_id: str
    message: str
    timestamp: float
    metadata: Dict[str, Any]  # Platform-specific data
    message_id: str = ""


@dataclass
class NormalizedResponse:
    """Response to send back to platform-specific format."""

    platform: str
    channel_id: str
    user_id: str
    content: str
    response_type: str  # 'message', 'thread_reply', 'dm', etc.
    metadata: Dict[str, Any]


class BaseAdapter(ABC):
    """
    Abstract base class for platform message adapters.

    Each adapter converts platform-specific message formats to unified schema
    and back, handling platform-specific quirks and rate limiting.
    """

    def __init__(self, platform_name: str) -> None:
        """Initialize adapter for a specific platform."""
        self.platform_name = platform_name
        self.logger = get_logger(f"{__name__}.{platform_name}")

    @abstractmethod
    async def normalize_message(self, raw_message: Dict[str, Any]) -> GatewayMessage:
        """
        Convert platform-specific message to unified schema.

        Both ``GatewayMessage.user_id`` (author id) and ``.message_id`` are
        mandatory (#14028) — ``user_id`` always has been (a required, no-default
        field every adapter already populates); ``message_id`` is the field this
        contract adds so the ingest governance stage in
        ``GatewayManager.normalize_message`` has a stable dedup key on every
        platform, not just the ones that happened to carry one in metadata.

        Args:
            raw_message: Platform-specific message object

        Returns:
            GatewayMessage in normalized format
        """

    @abstractmethod
    async def denormalize_response(self, unified_response: NormalizedResponse) -> Dict[str, Any]:
        """
        Convert unified response back to platform-specific format.

        Args:
            unified_response: Normalized response object

        Returns:
            Platform-specific response ready to send
        """

    @abstractmethod
    def get_rate_limit(self) -> Dict[str, int]:
        """
        Get rate limit configuration for this platform.

        Returns:
            Dict with keys: requests_per_second (int), burst_size (int)
        """

    async def validate_message(self, raw_message: Dict[str, Any]) -> bool:
        """
        Validate if raw message is well-formed for this platform.

        Can be overridden by subclasses for platform-specific validation.
        """
        # Base implementation - subclasses override with platform-specific rules
        return True

    async def extract_metadata(self, raw_message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract platform-specific metadata from message.

        Can be overridden by subclasses for richer metadata extraction.

        ``chain_depth`` (#14028) carries the agent-to-agent recursion counter
        forward from the raw payload so a chain that re-enters the Gateway
        (e.g. one agent's reply routed back in as another agent's inbound
        turn) keeps incrementing rather than resetting to 0 at each hop.
        """
        return {
            "raw_timestamp": raw_message.get("timestamp"),
            "thread_id": raw_message.get("thread_id"),
            "reply_to": raw_message.get("reply_to"),
            "chain_depth": int(raw_message.get("chain_depth", 0) or 0),
        }
