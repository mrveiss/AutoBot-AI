# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base Channel Adapter

Issue #732: Unified Gateway for multi-channel communication.
Defines the interface that all channel adapters must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..types import ChannelType, GatewaySession, UnifiedMessage


class BaseChannelAdapter(ABC):
    """
    Base class for all channel adapters.

    Channel adapters translate between channel-specific formats
    and the unified Gateway message format.
    """

    def __init__(self, channel_type: ChannelType):
        """
        Initialize the channel adapter.

        Args:
            channel_type: Type of channel this adapter handles
        """
        self.channel_type = channel_type

    @abstractmethod
    async def send_message(
        self,
        message: UnifiedMessage,
        session: GatewaySession,
        connection_context: Optional[Any] = None,
    ) -> bool:
        """
        Send a message through this channel.

        Args:
            message: Unified message to send
            session: Session associated with the message
            connection_context: Channel-specific connection context

        Returns:
            True if message sent successfully, False otherwise
        """

    @abstractmethod
    async def receive_message(
        self,
        raw_data: Any,
        session: GatewaySession,
    ) -> Optional[UnifiedMessage]:
        """
        Receive and parse a message from this channel.

        Args:
            raw_data: Raw channel-specific data
            session: Session associated with the message

        Returns:
            UnifiedMessage if parsed successfully, None otherwise
        """

    @abstractmethod
    async def connect(
        self,
        session: GatewaySession,
        connection_params: Dict[str, Any],
    ) -> Any:
        """
        Establish a connection for this channel.

        Args:
            session: Session to connect
            connection_params: Channel-specific connection parameters

        Returns:
            Connection context (e.g., WebSocket connection)
        """

    @abstractmethod
    async def disconnect(
        self,
        session: GatewaySession,
        connection_context: Optional[Any] = None,
    ) -> None:
        """
        Close a connection for this channel.

        Args:
            session: Session to disconnect
            connection_context: Channel-specific connection context
        """

    @abstractmethod
    async def handle_heartbeat(
        self,
        session: GatewaySession,
        connection_context: Optional[Any] = None,
    ) -> bool:
        """
        Handle heartbeat/keepalive for this channel.

        Args:
            session: Session to send heartbeat for
            connection_context: Channel-specific connection context

        Returns:
            True if heartbeat successful, False if connection lost
        """

    def validate_message_size(self, content: Any, max_size: int) -> bool:
        """
        Validate message size against limits.

        Args:
            content: Message content
            max_size: Maximum allowed size in bytes

        Returns:
            True if within limits, False otherwise
        """
        if isinstance(content, str):
            return len(content.encode("utf-8")) <= max_size
        elif isinstance(content, bytes):
            return len(content) <= max_size
        elif isinstance(content, dict):
            # Estimate size for dict/JSON
            import json

            return len(json.dumps(content).encode("utf-8")) <= max_size
        return True  # Unknown type, allow it
