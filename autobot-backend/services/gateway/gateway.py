# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Gateway Core Service

Issue #732: Unified Gateway for multi-channel communication.
Main Gateway class that coordinates session management, message routing,
and channel adapters.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from .channel_adapters.base import BaseChannelAdapter
from .config import GatewayConfig
from .message_router import MessageRouter
from .session_manager import SessionManager
from .types import ChannelType, GatewaySession, MessageType, UnifiedMessage

logger = logging.getLogger(__name__)


class Gateway:
    """
    Unified Gateway for multi-channel communication.

    The Gateway acts as a single control plane for all communication channels,
    providing:
    - Unified session management with isolation
    - Message routing to appropriate agents
    - Channel adapter interface for extensibility
    - Rate limiting and security controls
    """

    _instance: Optional["Gateway"] = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        """Singleton pattern for Gateway instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        config: Optional[GatewayConfig] = None,
        agent_router: Optional[Any] = None,
    ):
        """
        Initialize the Gateway.

        Args:
            config: Gateway configuration
            agent_router: Optional AgentRouter instance
        """
        # Prevent re-initialization
        if hasattr(self, "_initialized"):
            return

        self.config = config or GatewayConfig.from_env()
        self.session_manager = SessionManager(self.config)
        self.message_router = MessageRouter(agent_router)
        self._channel_adapters: Dict[ChannelType, BaseChannelAdapter] = {}
        self._connection_contexts: Dict[str, Any] = {}
        self._initialized = True
        self._started = False

        logger.info("Gateway initialized")

    async def start(self) -> None:
        """Start the Gateway service."""
        if self._started:
            return

        await self.session_manager.start()
        self._started = True
        logger.info("Gateway started")

    async def stop(self) -> None:
        """Stop the Gateway service."""
        if not self._started:
            return

        await self.session_manager.stop()

        # Close all active connections
        for session_id in list(self._connection_contexts.keys()):
            session = await self.session_manager.get_session(session_id)
            if session:
                adapter = self._channel_adapters.get(session.channel)
                if adapter:
                    await adapter.disconnect(
                        session,
                        self._connection_contexts.get(session_id),
                    )

        self._connection_contexts.clear()
        self._started = False
        logger.info("Gateway stopped")

    def register_channel_adapter(
        self,
        channel_type: ChannelType,
        adapter: BaseChannelAdapter,
    ) -> None:
        """
        Register a channel adapter.

        Args:
            channel_type: Type of channel
            adapter: Adapter instance
        """
        self._channel_adapters[channel_type] = adapter
        logger.info("Registered adapter for channel %s", channel_type.value)

    async def create_session(
        self,
        user_id: str,
        channel: ChannelType,
        connection_params: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
    ) -> GatewaySession:
        """
        Create a new Gateway session.

        Args:
            user_id: User identifier
            channel: Communication channel
            connection_params: Channel-specific connection parameters
            metadata: Optional session metadata

        Returns:
            Created session

        Raises:
            ValueError: If channel adapter not registered or session limit exceeded
        """
        # Verify channel adapter exists
        if channel not in self._channel_adapters:
            raise ValueError(f"No adapter registered for channel {channel.value}")

        # Create session
        session = await self.session_manager.create_session(
            user_id=user_id,
            channel=channel,
            metadata=metadata,
        )

        # Establish channel connection
        adapter = self._channel_adapters[channel]
        connection_context = await adapter.connect(
            session,
            connection_params or {},
        )

        # Store connection context
        self._connection_contexts[session.session_id] = connection_context

        # Send session start message
        start_message = UnifiedMessage(
            session_id=session.session_id,
            channel=channel,
            message_type=MessageType.SESSION_START,
            content={"session_id": session.session_id},
            metadata={"user_id": user_id},
        )

        await self.send_message(start_message)

        return session

    async def close_session(self, session_id: str) -> bool:
        """
        Close a Gateway session.

        Args:
            session_id: Session to close

        Returns:
            True if closed successfully
        """
        session = await self.session_manager.get_session(session_id)
        if not session:
            return False

        # Send session end message
        end_message = UnifiedMessage(
            session_id=session_id,
            channel=session.channel,
            message_type=MessageType.SESSION_END,
            content={"session_id": session_id},
        )

        await self.send_message(end_message)

        # Disconnect channel
        adapter = self._channel_adapters.get(session.channel)
        if adapter:
            connection_context = self._connection_contexts.get(session_id)
            await adapter.disconnect(session, connection_context)

        # Remove connection context
        if session_id in self._connection_contexts:
            del self._connection_contexts[session_id]

        # Close session
        return await self.session_manager.close_session(session_id)

    async def send_message(self, message: UnifiedMessage) -> bool:
        """
        Send a message through the Gateway.

        Args:
            message: Message to send

        Returns:
            True if sent successfully
        """
        # Get session
        session = await self.session_manager.get_session(message.session_id)
        if not session:
            logger.warning(
                "Cannot send message: session %s not found", message.session_id
            )
            return False

        # Get channel adapter
        adapter = self._channel_adapters.get(session.channel)
        if not adapter:
            logger.error("No adapter for channel %s", session.channel.value)
            return False

        # Validate message size
        if not adapter.validate_message_size(
            message.content,
            self.config.max_message_size_bytes,
        ):
            logger.warning("Message exceeds size limit")
            return False

        # Send through adapter
        connection_context = self._connection_contexts.get(message.session_id)
        success = await adapter.send_message(
            message,
            session,
            connection_context,
        )

        if success:
            # Update session
            session.add_message(message.message_id)

        return success

    async def receive_message(
        self,
        raw_data: Any,
        session_id: str,
    ) -> Optional[UnifiedMessage]:
        """
        Receive and parse a message from a channel.

        Args:
            raw_data: Raw channel-specific data
            session_id: Session receiving the message

        Returns:
            Parsed UnifiedMessage or None
        """
        # Get session
        session = await self.session_manager.get_session(session_id)
        if not session:
            logger.warning("Cannot receive message: session %s not found", session_id)
            return None

        # Check rate limit
        if not await self.session_manager.consume_rate_limit(session_id):
            logger.warning("Rate limit exceeded for session %s", session_id)
            # Send rate limit error
            error_msg = UnifiedMessage(
                session_id=session_id,
                channel=session.channel,
                message_type=MessageType.SYSTEM_ERROR,
                content={"error": "Rate limit exceeded. Please slow down."},
            )
            await self.send_message(error_msg)
            return None

        # Get adapter
        adapter = self._channel_adapters.get(session.channel)
        if not adapter:
            logger.error("No adapter for channel %s", session.channel.value)
            return None

        # Parse message
        message = await adapter.receive_message(raw_data, session)
        if message:
            session.add_message(message.message_id)

        return message

    async def route_and_process(
        self,
        message: UnifiedMessage,
        context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Route a message and process with appropriate agent.

        Args:
            message: Message to route
            context: Optional routing context

        Returns:
            Processing result with agent type and response
        """
        # Route message
        routing = await self.message_router.route_message(message, context)

        logger.info(
            "Routed message %s to agent %s (confidence: %.2f)",
            message.message_id,
            routing.agent_type,
            routing.confidence,
        )

        # TODO: Integrate with agent execution
        # For now, return routing decision
        return {
            "message_id": message.message_id,
            "agent_type": routing.agent_type,
            "confidence": routing.confidence,
            "reasoning": routing.reasoning,
        }

    async def get_stats(self) -> Dict[str, Any]:
        """Get Gateway statistics."""
        session_stats = await self.session_manager.get_stats()
        routing_stats = await self.message_router.get_routing_stats()

        return {
            "gateway": {
                "started": self._started,
                "channels_registered": len(self._channel_adapters),
                "active_connections": len(self._connection_contexts),
            },
            "sessions": session_stats,
            "routing": routing_stats,
        }


# Singleton instance getter
_gateway_instance: Optional[Gateway] = None


async def get_gateway() -> Gateway:
    """Get the singleton Gateway instance."""
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = Gateway()
        await _gateway_instance.start()
    return _gateway_instance
