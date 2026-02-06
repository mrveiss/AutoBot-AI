# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat Agent - Specialized for conversational interactions.

Handles simple conversational responses with lightweight Llama 3.2 1B model.
Focuses on quick, natural interactions without complex reasoning.
"""

import logging
from typing import Any, Dict, List, Optional

from autobot_shared.ssot_config import (
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)
from constants.threshold_constants import LLMDefaults
from llm_interface import LLMInterface

from .base_agent import AgentRequest
from .standardized_agent import ActionHandler, StandardizedAgent

logger = logging.getLogger(__name__)


class ChatAgent(StandardizedAgent):
    """Lightweight chat agent for quick conversational responses."""

    # Agent identifier for SSOT config lookup
    AGENT_ID = "chat"

    def __init__(self):
        """Initialize the Chat Agent with explicit LLM configuration (no fallbacks)."""
        super().__init__("chat")
        self.llm_interface = LLMInterface()

        # Use explicit SSOT config - raises AgentConfigurationError if not set
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)
        self.capabilities = [
            "conversational_chat",
            "simple_questions",
            "greetings",
            "basic_explanations",
        ]

        # Register action handlers using standardized pattern
        self.register_actions(
            {
                "chat": ActionHandler(
                    handler_method="handle_chat",
                    required_params=["message"],
                    optional_params=["context", "chat_history"],
                    description="Process chat messages",
                )
            }
        )

        logger.info(
            "Chat Agent initialized with provider=%s, endpoint=%s, model=%s",
            self.llm_provider,
            self.llm_endpoint,
            self.model_name,
        )

    async def handle_chat(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle chat action - replaces duplicate process_request logic"""
        message = request.payload["message"]
        context = request.context or {}
        chat_history = request.payload.get("chat_history", [])

        result = await self.process_chat_message(message, context, chat_history)
        return result

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports."""
        return self.capabilities.copy()

    def _build_success_response(
        self, response_text: str, response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build success response dictionary for chat message processing.

        Issue #620.
        """
        return {
            "status": "success",
            "response_text": response_text,
            "agent_type": "chat",
            "model_used": self.model_name,
            "token_usage": response.get("usage", {}),
            "metadata": {
                "agent": "ChatAgent",
                "processing_time": "fast",
                "complexity": "low",
            },
        }

    def _build_error_response(self, error: Exception) -> Dict[str, Any]:
        """
        Build error response dictionary for chat message processing.

        Issue #620.
        """
        return {
            "status": "error",
            "response_text": (
                "I'm having trouble processing your message right now. "
                "Could you try rephrasing it?"
            ),
            "error": str(error),
            "agent_type": "chat",
            "model_used": self.model_name,
        }

    async def process_chat_message(
        self,
        message: str,
        context: Optional[List[Dict[str, str]]] = None,
        chat_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Process a conversational message and generate appropriate response.

        Args:
            message: User's chat message
            context: Optional conversation context
            chat_history: Optional chat history for context

        Returns:
            Dict containing the chat response and metadata

        Issue #620: Refactored to use extracted helper methods.
        """
        try:
            logger.info("Chat Agent processing message: %s...", message[:50])

            # Prepare chat-optimized system prompt
            system_prompt = self._get_chat_system_prompt()

            # Build conversation context
            messages = [{"role": "system", "content": system_prompt}]

            # Add recent chat history if available (limit to last 6 messages for 1B model)
            if chat_history:
                messages.extend(self._build_history_messages(chat_history))

            # Add current message
            messages.append({"role": "user", "content": message})

            # Generate response using optimized settings for chat
            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="chat",  # This will use the chat-specific model
                temperature=LLMDefaults.DEFAULT_TEMPERATURE,
                max_tokens=LLMDefaults.CHAT_MAX_TOKENS,
                top_p=LLMDefaults.DEFAULT_TOP_P,
            )

            # Extract response content and build response
            response_text = self._extract_response_content(response)
            return self._build_success_response(response_text, response)

        except Exception as e:
            logger.error("Chat Agent error processing message: %s", e)
            return self._build_error_response(e)

    def _get_chat_system_prompt(self) -> str:
        """Get optimized system prompt for chat interactions."""
        return """You are a helpful, friendly AI assistant focused on conversational interactions.

Key Guidelines:
- Provide clear, concise responses
- Be natural and conversational
- Keep responses focused and relevant
- If you don't know something, say so honestly
- For complex tasks, acknowledge them but suggest they might need specialized handling
- Maintain a helpful and positive tone

You specialize in:
- General conversation
- Simple questions and answers
- Basic explanations
- Friendly interactions

For complex technical tasks, analysis, or system commands, you should "
        "indicate that specialized agents can handle those better."""

    def _build_history_messages(
        self, chat_history: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """Build message list from chat history (Issue #334 - extracted helper)."""
        messages = []
        recent_history = chat_history[-6:] if len(chat_history) > 6 else chat_history
        role_map = {"user": "user", "bot": "assistant"}

        for msg in recent_history:
            sender = msg.get("sender")
            role = role_map.get(sender)
            if role:
                messages.append({"role": role, "content": msg.get("text", "")})

        return messages

    def _try_extract_message_content(self, response: Dict) -> Optional[str]:
        """Try to extract content from message dict (Issue #334 - extracted helper)."""
        if "message" not in response:
            return None
        message = response["message"]
        if not isinstance(message, dict):
            return None
        content = message.get("content")
        return content.strip() if content else None

    def _try_extract_choices_content(self, response: Dict) -> Optional[str]:
        """Try to extract content from choices list (Issue #334 - extracted helper)."""
        if "choices" not in response:
            return None
        choices = response["choices"]
        if not isinstance(choices, list) or not choices:
            return None
        choice = choices[0]
        if "message" not in choice or "content" not in choice["message"]:
            return None
        return choice["message"]["content"].strip()

    def _extract_response_content(self, response: Any) -> str:
        """Extract the actual text content from LLM response."""
        try:
            if isinstance(response, dict):
                # Try message content first
                content = self._try_extract_message_content(response)
                if content:
                    return content

                # Try choices format
                content = self._try_extract_choices_content(response)
                if content:
                    return content

                # Check for direct content
                if "content" in response:
                    return response["content"].strip()

            if isinstance(response, str):
                return response.strip()

            return str(response)

        except Exception as e:
            logger.error("Error extracting response content: %s", e)
            return "I had trouble generating a proper response. Please try again."

    def _get_chat_patterns(self) -> List[str]:
        """
        Return list of simple conversational patterns for chat routing.

        Issue #620.
        """
        return [
            "hello",
            "hi",
            "hey",
            "good morning",
            "good afternoon",
            "good evening",
            "how are you",
            "what's up",
            "thanks",
            "thank you",
            "goodbye",
            "bye",
            "tell me about",
            "explain",
            "what is",
            "who is",
            "where is",
            "when",
            "help",
            "please",
            "can you",
            "would you",
            "could you",
        ]

    def _get_complex_patterns(self) -> List[str]:
        """
        Return list of complex task patterns that should be routed elsewhere.

        Issue #620.
        """
        return [
            "execute",
            "run command",
            "system",
            "install",
            "download",
            "search knowledge",
            "find documents",
            "research",
            "web search",
            "analyze",
            "calculate",
            "compute",
            "code",
            "script",
            "program",
        ]

    def is_chat_appropriate(self, message: str) -> bool:
        """
        Determine if a message is appropriate for the chat agent.

        Args:
            message: The user's message

        Returns:
            bool: True if chat agent should handle it, False if needs routing

        Issue #620: Refactored to use extracted helper methods.
        """
        message_lower = message.lower()

        # Check if it's a complex task
        if any(pattern in message_lower for pattern in self._get_complex_patterns()):
            return False

        # Check if it's conversational
        if any(pattern in message_lower for pattern in self._get_chat_patterns()):
            return True

        # Default to chat for short, simple messages
        return len(message.split()) <= 10


# Singleton instance (thread-safe)
import threading

_chat_agent_instance = None
_chat_agent_lock = threading.Lock()


def get_chat_agent() -> ChatAgent:
    """Get the singleton Chat Agent instance (thread-safe)."""
    global _chat_agent_instance
    if _chat_agent_instance is None:
        with _chat_agent_lock:
            # Double-check after acquiring lock
            if _chat_agent_instance is None:
                _chat_agent_instance = ChatAgent()
    return _chat_agent_instance
