# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Multi-Platform Message Gateway

Central gateway that normalizes messages from 9+ platforms (Web, Slack, Discord,
WhatsApp, Teams, Telegram, Signal, Matrix, iMessage) into a unified schema.
Enables a single agent to serve all channels.

Features:
- Unified message schema: {user_id, platform, channel_id, message, metadata}
- Per-platform adapters handling request/response normalization
- Rate limiting per platform (Slack 1 req/s, Discord 10 req/s, etc.)
- Message queue with async processing
- Performance target: normalize + route <50ms
- Optional adapters gated by env flags: Signal (AUTOBOT_SIGNAL_ENABLED),
  iMessage (AUTOBOT_IMESSAGE_ENABLED, macOS-only)
"""

import time
from typing import Any, Callable, Dict, List

from autobot_shared.logging_manager import get_logger

from .adapters import (
    BaseAdapter,
    DiscordAdapter,
    IMessageAdapter,
    MatrixAdapter,
    NormalizedResponse,
    SignalAdapter,
    SlackAdapter,
    TeamsAdapter,
    TelegramAdapter,
    UnifiedMessage,
    WebAdapter,
    WhatsAppAdapter,
)
from .message_queue import MessageQueue

logger = get_logger(__name__)


class GatewayManager:
    """
    Central gateway managing message normalization from multiple platforms.

    Coordinates platform adapters, message queue, and rate limiting to provide
    unified interface for agent to serve all channels.
    """

    def __init__(self) -> None:
        """Initialize gateway with all platform adapters."""
        self.adapters: Dict[str, BaseAdapter] = {}
        self.queue = MessageQueue()
        self.response_handlers: Dict[str, Callable] = {}
        self.logger = get_logger(__name__)

        # Register all platform adapters
        self._register_adapters()

    def _register_adapters(self) -> None:
        """Register all supported platform adapters."""
        adapters = [
            WebAdapter(),
            SlackAdapter(),
            DiscordAdapter(),
            WhatsAppAdapter(),
            TeamsAdapter(),
            TelegramAdapter(),
            SignalAdapter(),
            MatrixAdapter(),
            IMessageAdapter(),
        ]

        for adapter in adapters:
            self.adapters[adapter.platform_name] = adapter
            limits = adapter.get_rate_limit()
            self.queue.register_platform(
                adapter.platform_name,
                limits["requests_per_second"],
                limits["burst_size"],
            )
            self.logger.info(f"Registered adapter for platform: {adapter.platform_name}")

    def register_response_handler(self, platform: str, handler: Callable[[NormalizedResponse], None]) -> None:
        """
        Register handler for platform responses.

        Args:
            platform: Platform name (e.g., 'slack', 'discord')
            handler: Async callable(NormalizedResponse) -> None
        """
        self.response_handlers[platform] = handler
        self.logger.info(f"Registered response handler for platform: {platform}")

    async def normalize_message(self, raw_message: Dict[str, Any]) -> UnifiedMessage:
        """
        Normalize a raw platform-specific message to unified schema.

        Performance target: <50ms including validation and metadata extraction.

        Args:
            raw_message: Platform-specific message dict with 'platform' key

        Returns:
            UnifiedMessage in normalized format

        Raises:
            ValueError: If platform not supported or validation fails
        """
        start_time = time.time()

        platform = raw_message.get("platform")
        if not platform:
            raise ValueError("Message missing required 'platform' field")

        if platform not in self.adapters:
            raise ValueError(f"Unsupported platform: {platform}")

        adapter = self.adapters[platform]

        # Validate message format
        if not await adapter.validate_message(raw_message):
            raise ValueError(f"Invalid message format for platform {platform}")

        # Normalize to unified schema
        unified = await adapter.normalize_message(raw_message)

        elapsed_ms = (time.time() - start_time) * 1000
        if elapsed_ms > 50:
            self.logger.warning(f"Normalization for {platform} took {elapsed_ms:.1f}ms (>50ms target)")

        self.logger.debug(f"Normalized message from {platform} user {unified.user_id} in {elapsed_ms:.1f}ms")
        return unified

    async def denormalize_response(self, unified_response: NormalizedResponse) -> Dict[str, Any]:
        """
        Convert unified response back to platform-specific format.

        Args:
            unified_response: Normalized response object

        Returns:
            Platform-specific response dict ready to send

        Raises:
            ValueError: If platform not supported
        """
        platform = unified_response.platform

        if platform not in self.adapters:
            raise ValueError(f"Unsupported platform: {platform}")

        adapter = self.adapters[platform]
        platform_response = await adapter.denormalize_response(unified_response)

        self.logger.debug(f"Denormalized response for platform {platform}")
        return platform_response

    async def route_message(
        self,
        unified_message: UnifiedMessage,
        agent_handler: Callable[[UnifiedMessage], Dict[str, Any]],
    ) -> None:
        """
        Route normalized message through agent and send response to platform.

        Args:
            unified_message: Normalized message from any platform
            agent_handler: Async handler returning response dict
        """
        try:
            # Process message through agent
            response_data = await agent_handler(unified_message)

            # Build normalized response
            unified_response = NormalizedResponse(
                platform=unified_message.platform,
                channel_id=unified_message.channel_id,
                user_id=unified_message.user_id,
                content=response_data.get("response", ""),
                response_type=response_data.get("type", "message"),
                metadata=response_data.get("metadata", {}),
            )

            # Denormalize to platform format
            platform_response = await self.denormalize_response(unified_response)

            # Send via platform-specific handler
            if unified_message.platform in self.response_handlers:
                handler = self.response_handlers[unified_message.platform]
                await handler(platform_response)
                self.logger.debug(f"Routed response to {unified_message.platform} handler")
        except Exception as e:
            self.logger.error(f"Error routing message: {e}", exc_info=True)

    async def enqueue_message(self, raw_message: Dict[str, Any]) -> None:
        """
        Enqueue raw message for processing.

        Args:
            raw_message: Platform-specific message dict
        """
        await self.queue.enqueue(raw_message)

    async def start_processing(
        self,
        agent_handler: Callable[[UnifiedMessage], Dict[str, Any]],
        workers: int = 5,
    ) -> None:
        """
        Start message queue processing with specified worker count.

        Args:
            agent_handler: Async handler for normalized messages
            workers: Number of concurrent workers
        """

        async def message_processor(raw_message: Dict[str, Any]) -> None:
            try:
                unified = await self.normalize_message(raw_message)
                await self.route_message(unified, agent_handler)
            except Exception as e:
                self.logger.error(
                    f"Error processing message from {raw_message.get('platform')}: {e}",
                    exc_info=True,
                )

        await self.queue.process_queue(message_processor, workers=workers)

    async def shutdown(self) -> None:
        """Shutdown gateway and message queue."""
        self.logger.info("Shutting down gateway")
        await self.queue.shutdown()

    def get_adapter(self, platform: str) -> BaseAdapter | None:
        """Get adapter for platform."""
        return self.adapters.get(platform)

    def get_supported_platforms(self) -> List[str]:
        """Get list of supported platforms."""
        return list(self.adapters.keys())
