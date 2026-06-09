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
class UnifiedMessage:
    """Unified message schema normalized from all platforms."""

    user_id: str
    platform: str  # 'web', 'slack', 'discord', 'whatsapp', 'teams'
    channel_id: str
    message: str
    timestamp: float
    metadata: Dict[str, Any]  # Platform-specific data


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
    async def normalize_message(self, raw_message: Dict[str, Any]) -> UnifiedMessage:
        """
        Convert platform-specific message to unified schema.

        Args:
            raw_message: Platform-specific message object

        Returns:
            UnifiedMessage in normalized format
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
        """
        return {
            "raw_timestamp": raw_message.get("timestamp"),
            "thread_id": raw_message.get("thread_id"),
            "reply_to": raw_message.get("reply_to"),
        }
