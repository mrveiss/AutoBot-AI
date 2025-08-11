"""
Chat Agent - Specialized for conversational interactions.

Handles simple conversational responses with lightweight Llama 3.2 1B model.
Focuses on quick, natural interactions without complex reasoning.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from src.config import config as global_config_manager
from src.llm_interface import LLMInterface

logger = logging.getLogger(__name__)


class ChatAgent:
    """Lightweight chat agent for quick conversational responses."""

    def __init__(self):
        """Initialize the Chat Agent with 1B model for efficiency."""
        self.llm_interface = LLMInterface()
        self.model_name = global_config_manager.get_task_specific_model("chat")
        self.agent_type = "chat"

        logger.info(f"Chat Agent initialized with model: {self.model_name}")

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
        """
        try:
            logger.info(f"Chat Agent processing message: {message[:50]}...")

            # Prepare chat-optimized system prompt
            system_prompt = self._get_chat_system_prompt()

            # Build conversation context
            messages = [{"role": "system", "content": system_prompt}]

            # Add recent chat history if available (limit to last 6 messages for 1B model)
            if chat_history:
                recent_history = (
                    chat_history[-6:] if len(chat_history) > 6 else chat_history
                )
                for msg in recent_history:
                    if msg.get("sender") == "user":
                        messages.append(
                            {"role": "user", "content": msg.get("text", "")}
                        )
                    elif msg.get("sender") == "bot":
                        messages.append(
                            {"role": "assistant", "content": msg.get("text", "")}
                        )

            # Add current message
            messages.append({"role": "user", "content": message})

            # Generate response using optimized settings for chat
            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="chat",  # This will use the chat-specific model
                temperature=0.7,  # Slightly creative for natural conversation
                max_tokens=512,  # Limit tokens for quick responses
                top_p=0.9,
            )

            # Extract response content
            response_text = self._extract_response_content(response)

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

        except Exception as e:
            logger.error(f"Chat Agent error processing message: {e}")
            return {
                "status": "error",
                "response_text": "I'm having trouble processing your message right now. Could you try rephrasing it?",
                "error": str(e),
                "agent_type": "chat",
                "model_used": self.model_name,
            }

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

For complex technical tasks, analysis, or system commands, you should indicate that specialized agents can handle those better."""

    def _extract_response_content(self, response: Any) -> str:
        """Extract the actual text content from LLM response."""
        try:
            # Handle different response formats from LLM interface
            if isinstance(response, dict):
                # Check for message content
                if "message" in response and isinstance(response["message"], dict):
                    content = response["message"].get("content")
                    if content:
                        return content.strip()

                # Check for choices format
                if "choices" in response and isinstance(response["choices"], list):
                    if len(response["choices"]) > 0:
                        choice = response["choices"][0]
                        if "message" in choice and "content" in choice["message"]:
                            return choice["message"]["content"].strip()

                # Check for direct content
                if "content" in response:
                    return response["content"].strip()

            # Fallback to string conversion
            if isinstance(response, str):
                return response.strip()

            return str(response)

        except Exception as e:
            logger.error(f"Error extracting response content: {e}")
            return "I had trouble generating a proper response. Please try again."

    def is_chat_appropriate(self, message: str) -> bool:
        """
        Determine if a message is appropriate for the chat agent.

        Args:
            message: The user's message

        Returns:
            bool: True if chat agent should handle it, False if needs routing
        """
        # Simple conversational patterns
        chat_patterns = [
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

        # Complex task patterns that should be routed elsewhere
        complex_patterns = [
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

        message_lower = message.lower()

        # Check if it's a complex task
        if any(pattern in message_lower for pattern in complex_patterns):
            return False

        # Check if it's conversational
        if any(pattern in message_lower for pattern in chat_patterns):
            return True

        # Default to chat for short, simple messages
        return len(message.split()) <= 10


# Singleton instance
_chat_agent_instance = None


def get_chat_agent() -> ChatAgent:
    """Get the singleton Chat Agent instance."""
    global _chat_agent_instance
    if _chat_agent_instance is None:
        _chat_agent_instance = ChatAgent()
    return _chat_agent_instance
