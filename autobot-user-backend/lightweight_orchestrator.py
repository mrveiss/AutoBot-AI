# src/lightweight_orchestrator.py
"""
Lightweight Orchestrator - Non-blocking replacement for the main orchestrator

This orchestrator eliminates all blocking operations that were causing 30+ second delays:
- No Redis pubsub blocking calls
- No expensive LLM classification for administrative endpoints
- Simple pattern-based routing for common operations
- Only uses complex orchestration when absolutely necessary
"""

import logging
import re
from typing import Any, Dict, Optional

from autobot_types import TaskComplexity

from backend.patterns.conversation_patterns import (
    ConversationPatterns,
    ConversationType,
)

logger = logging.getLogger(__name__)


class LightweightOrchestrator:
    """
    High-performance orchestrator that avoids blocking operations.

    Key design principles:
    1. No synchronous Redis calls in async functions
    2. No LLM classification for simple/administrative requests
    3. Pattern-based routing for common operations
    4. Falls back to full orchestrator only when needed
    """

    def __init__(self):
        self.conversation_patterns = ConversationPatterns()

        # Administrative endpoints that should never trigger LLM classification
        self.admin_endpoints = {
            "/api/chats",
            "/api/settings",
            "/api/system",
            "/api/llm",
            "/api/hello",
            "/api/version",
            "/api/metrics",
        }

        # Simple conversational patterns that don't need orchestration
        self.simple_patterns = [
            re.compile(r"^(hello|hi|hey)!?$", re.IGNORECASE),
            re.compile(r"^(thanks?|thank you)!?$", re.IGNORECASE),
            re.compile(r"^(bye|goodbye|see you)!?$", re.IGNORECASE),
            re.compile(r"^(ok|okay|yes|no)!?$", re.IGNORECASE),
        ]

    async def startup(self):
        """Lightweight startup - no blocking operations."""
        logger.info(
            "LightweightOrchestrator started successfully (no blocking operations)"
        )

    async def should_bypass_orchestration(
        self, request_path: str, user_message: str = ""
    ) -> bool:
        """
        Determine if a request should bypass full orchestration.

        Args:
            request_path: The API endpoint path being called
            user_message: Optional message content for pattern matching

        Returns:
            bool: True if orchestration should be bypassed
        """
        # Always bypass for administrative endpoints
        if any(admin_path in request_path for admin_path in self.admin_endpoints):
            logger.debug(f"Bypassing orchestration for admin endpoint: {request_path}")
            return True

        # Bypass for simple conversational patterns
        if user_message:
            message_clean = user_message.strip()
            if any(pattern.match(message_clean) for pattern in self.simple_patterns):
                logger.debug(
                    f"Bypassing orchestration for simple message: {message_clean}"
                )
                return True

            # Use conversation patterns for classification
            conv_type = self.conversation_patterns.classify_message(message_clean)
            if conv_type in [
                ConversationType.GREETING,
                ConversationType.ACKNOWLEDGMENT,
            ]:
                logger.debug(
                    f"Bypassing orchestration for {conv_type.value}: {message_clean}"
                )
                return True

        return False

    async def get_simple_response(self, user_message: str) -> Optional[str]:
        """
        Get a simple response for basic conversational patterns.

        Args:
            user_message: The user's message

        Returns:
            Optional[str]: Simple response or None if no pattern matches
        """
        message_clean = user_message.strip()
        conv_type = self.conversation_patterns.classify_message(message_clean)

        if conv_type == ConversationType.GREETING:
            return "Hello! How can I help you today?"
        elif conv_type == ConversationType.ACKNOWLEDGMENT:
            return "You're welcome!"
        elif message_clean.lower() in ["bye", "goodbye", "see you"]:
            return "Goodbye! Feel free to ask if you need anything else."
        elif message_clean.lower() in ["ok", "okay"]:
            return "Understood!"

        return None

    async def classify_request_complexity_lightweight(
        self, user_message: str
    ) -> TaskComplexity:
        """
        Lightweight complexity classification without expensive LLM calls.

        Uses pattern matching and heuristics instead of LLM classification
        for common cases.
        """
        message_lower = user_message.lower()

        # Simple conversational responses
        if any(pattern.match(user_message.strip()) for pattern in self.simple_patterns):
            return TaskComplexity.SIMPLE

        # System/admin queries
        if any(
            word in message_lower for word in ["status", "config", "setting", "list"]
        ):
            return TaskComplexity.SIMPLE

        # Complex operations
        complex_keywords = [
            "analyze",
            "research",
            "install",
            "configure",
            "create",
            "build",
            "deploy",
            "debug",
            "troubleshoot",
            "automate",
        ]
        if any(keyword in message_lower for keyword in complex_keywords):
            return TaskComplexity.COMPLEX

        # Code-related requests
        if any(
            word in message_lower for word in ["code", "script", "function", "class"]
        ):
            return TaskComplexity.MODERATE

        # Default to simple to avoid unnecessary overhead
        return TaskComplexity.SIMPLE

    async def route_request(
        self, request_path: str, user_message: str = ""
    ) -> Dict[str, Any]:
        """
        Route request based on lightweight analysis.

        Args:
            request_path: API endpoint path
            user_message: Optional message content

        Returns:
            Dict containing routing decision and metadata
        """
        should_bypass = await self.should_bypass_orchestration(
            request_path, user_message
        )

        if should_bypass:
            simple_response = None
            if user_message:
                simple_response = await self.get_simple_response(user_message)

            return {
                "bypass_orchestration": True,
                "complexity": TaskComplexity.SIMPLE,
                "simple_response": simple_response,
                "routing_reason": "lightweight_pattern_match",
            }
        else:
            complexity = await self.classify_request_complexity_lightweight(
                user_message
            )
            return {
                "bypass_orchestration": False,
                "complexity": complexity,
                "simple_response": None,
                "routing_reason": "requires_full_orchestration",
            }


# Global instance for use across the application
lightweight_orchestrator = LightweightOrchestrator()
