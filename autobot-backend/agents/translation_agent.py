# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Translation Agent - Specialized for multi-language translation support.

Handles text translation between languages with context-aware processing
and automatic language detection.
"""

import logging
import threading
from typing import Any, Dict, List, Optional

from constants.threshold_constants import LLMDefaults
from llm_interface import LLMInterface

from autobot_shared.ssot_config import (
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)

from .base_agent import AgentRequest
from .standardized_agent import ActionHandler, StandardizedAgent

logger = logging.getLogger(__name__)


class TranslationAgent(StandardizedAgent):
    """Agent specialized for multi-language translation."""

    AGENT_ID = "translation"

    def __init__(self):
        """Initialize the Translation Agent with LLM configuration."""
        super().__init__("translation")
        self.llm_interface = LLMInterface()
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)
        self.capabilities = [
            "language_translation",
            "language_detection",
            "multilingual_support",
            "context_aware_translation",
        ]
        self._register_action_handlers()
        logger.info(
            "Translation Agent initialized: provider=%s, model=%s",
            self.llm_provider,
            self.model_name,
        )

    def _register_action_handlers(self):
        """Register action handlers for translation operations."""
        self.register_actions(
            {
                "translate": ActionHandler(
                    handler_method="handle_translate",
                    required_params=["text", "target_language"],
                    optional_params=["source_language", "context"],
                    description="Translate text to target language",
                ),
                "detect_language": ActionHandler(
                    handler_method="handle_detect_language",
                    required_params=["text"],
                    description="Detect the language of input text",
                ),
            }
        )

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports."""
        return self.capabilities.copy()

    async def handle_translate(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle translation action."""
        text = request.payload["text"]
        target = request.payload["target_language"]
        source = request.payload.get("source_language", "auto-detect")
        prompt = (
            f"Translate the following text from {source} to {target}. "
            f"Preserve the original meaning, tone, and formatting.\n\nText:\n{text}"
        )
        return await self.process_query(prompt)

    async def handle_detect_language(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle language detection action."""
        text = request.payload["text"]
        prompt = (
            "Identify the language of the following text. Respond with a JSON object "
            'containing "language" (ISO 639-1 code), "language_name" (full name), '
            f'and "confidence" (0-1 score).\n\nText:\n{text}'
        )
        return await self.process_query(prompt)

    async def process_query(
        self, request_text: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a translation query using LLM."""
        try:
            logger.info("Translation Agent processing: %s...", request_text[:50])
            messages = [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": request_text},
            ]
            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="chat",
                temperature=0.3,
                max_tokens=LLMDefaults.CHAT_MAX_TOKENS,
                top_p=LLMDefaults.DEFAULT_TOP_P,
            )
            response_text = self._extract_content(response)
            return {
                "status": "success",
                "response": response_text,
                "response_text": response_text,
                "agent_type": "translation",
                "model_used": self.model_name,
                "token_usage": response.get("usage", {})
                if isinstance(response, dict)
                else {},
            }
        except Exception as e:
            logger.error("Translation Agent error: %s", e)
            return {
                "status": "error",
                "response": "Error processing translation. Please try again.",
                "response_text": str(e),
                "agent_type": "translation",
                "model_used": self.model_name,
            }

    def _get_system_prompt(self) -> str:
        """Get system prompt for translation tasks."""
        return (
            "You are an expert multilingual translator. Your role is to provide "
            "accurate, natural-sounding translations.\n\n"
            "Guidelines:\n"
            "- Preserve the original meaning, tone, and intent\n"
            "- Use idiomatic expressions appropriate to the target language\n"
            "- Maintain formatting (paragraphs, bullet points, etc.)\n"
            "- For ambiguous terms, choose the most contextually appropriate translation\n"
            "- If detecting language, provide ISO 639-1 code and confidence level\n"
            "- Handle technical terminology with precision"
        )

    def _extract_content(self, response: Any) -> str:
        """Extract text content from LLM response."""
        if isinstance(response, str):
            return response.strip()
        if isinstance(response, dict):
            msg = response.get("message", {})
            if isinstance(msg, dict) and msg.get("content"):
                return msg["content"].strip()
            choices = response.get("choices", [])
            if choices and isinstance(choices[0], dict):
                choice_msg = choices[0].get("message", {})
                if isinstance(choice_msg, dict) and choice_msg.get("content"):
                    return choice_msg["content"].strip()
            if "content" in response:
                return str(response["content"]).strip()
        return str(response)


_translation_agent_instance = None
_translation_agent_lock = threading.Lock()


def get_translation_agent() -> TranslationAgent:
    """Get the singleton Translation Agent instance (thread-safe)."""
    global _translation_agent_instance
    if _translation_agent_instance is None:
        with _translation_agent_lock:
            if _translation_agent_instance is None:
                _translation_agent_instance = TranslationAgent()
    return _translation_agent_instance
