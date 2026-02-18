# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Gateway Message Router

Issue #732: Unified Gateway for multi-channel communication.
Routes messages to appropriate agents based on content and context.
"""

import logging
from typing import Any, Dict, Optional

from .types import MessageType, RoutingDecision, UnifiedMessage

logger = logging.getLogger(__name__)


class MessageRouter:
    """
    Routes messages to appropriate agents.

    Delegates to the existing agent orchestration routing logic
    while providing a simplified Gateway-specific interface.
    """

    def __init__(self, agent_router: Optional[Any] = None):
        """
        Initialize the message router.

        Args:
            agent_router: Optional existing AgentRouter instance
                         (from agents.agent_orchestration.routing)
        """
        self._agent_router = agent_router

    def set_agent_router(self, agent_router: Any) -> None:
        """
        Set the agent router (for lazy initialization).

        Args:
            agent_router: AgentRouter instance
        """
        self._agent_router = agent_router

    async def route_message(
        self,
        message: UnifiedMessage,
        context: Optional[Dict[str, Any]] = None,
    ) -> RoutingDecision:
        """
        Route a message to the appropriate agent.

        Args:
            message: Message to route
            context: Optional routing context

        Returns:
            RoutingDecision with agent type and confidence
        """
        # Handle system messages (no routing needed)
        if self._is_system_message(message):
            return RoutingDecision(
                agent_type="system",
                confidence=1.0,
                reasoning="System message",
            )

        # Handle non-text messages
        if message.message_type == MessageType.USER_VOICE:
            return RoutingDecision(
                agent_type="voice_transcription",
                confidence=1.0,
                reasoning="Voice message requires transcription",
            )
        elif message.message_type == MessageType.USER_IMAGE:
            return RoutingDecision(
                agent_type="image_analysis",
                confidence=1.0,
                reasoning="Image message requires vision analysis",
            )

        # For text messages, delegate to agent router
        if self._agent_router and message.message_type == MessageType.USER_TEXT:
            try:
                routing_result = await self._agent_router.determine_routing(
                    request=str(message.content),
                    context=context or {},
                )

                return RoutingDecision(
                    agent_type=routing_result.get("agent_type", "chat"),
                    confidence=routing_result.get("confidence", 0.5),
                    reasoning=routing_result.get("reasoning", ""),
                    metadata=routing_result,
                )
            except Exception as e:
                logger.error("Error in agent routing: %s", e, exc_info=True)
                # Fallback to chat agent
                return RoutingDecision(
                    agent_type="chat",
                    confidence=0.5,
                    reasoning=f"Fallback due to routing error: {e}",
                )

        # Default fallback
        return RoutingDecision(
            agent_type="chat",
            confidence=0.5,
            reasoning="Default chat agent",
        )

    def _is_system_message(self, message: UnifiedMessage) -> bool:
        """Check if message is a system control message."""
        return message.message_type in {
            MessageType.SYSTEM_STATUS,
            MessageType.SYSTEM_ERROR,
            MessageType.SYSTEM_PROGRESS,
            MessageType.SESSION_START,
            MessageType.SESSION_END,
            MessageType.SESSION_HEARTBEAT,
        }

    async def get_routing_stats(self) -> Dict[str, Any]:
        """
        Get routing statistics.

        Returns:
            Dictionary with routing metrics
        """
        # TODO: Implement routing stats tracking
        return {
            "total_routes": 0,
            "routes_by_agent": {},
            "average_confidence": 0.0,
        }
