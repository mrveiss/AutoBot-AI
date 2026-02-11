# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Summarization Agent - Specialized for document and text summarization.

Handles text summarization with configurable length, key point extraction,
and structured summary generation.
"""

import logging
import threading
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


class SummarizationAgent(StandardizedAgent):
    """Agent specialized for document and text summarization."""

    AGENT_ID = "summarization"

    def __init__(self):
        """Initialize the Summarization Agent with LLM configuration."""
        super().__init__("summarization")
        self.llm_interface = LLMInterface()
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)
        self.capabilities = [
            "text_summarization",
            "key_point_extraction",
            "document_condensation",
            "abstractive_summary",
        ]
        self._register_action_handlers()
        logger.info(
            "Summarization Agent initialized: provider=%s, model=%s",
            self.llm_provider,
            self.model_name,
        )

    def _register_action_handlers(self):
        """Register action handlers for summarization operations."""
        self.register_actions(
            {
                "summarize": ActionHandler(
                    handler_method="handle_summarize",
                    required_params=["text"],
                    optional_params=["max_length", "style"],
                    description="Summarize text content",
                ),
                "extract_key_points": ActionHandler(
                    handler_method="handle_extract_key_points",
                    required_params=["text"],
                    optional_params=["max_points"],
                    description="Extract key points from text",
                ),
            }
        )

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports."""
        return self.capabilities.copy()

    async def handle_summarize(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle summarization action."""
        text = request.payload["text"]
        max_length = request.payload.get("max_length", "medium")
        style = request.payload.get("style", "concise")
        prompt = f"Provide a {style} summary ({max_length} length) of the following text:\n\n{text}"
        return await self.process_query(prompt)

    async def handle_extract_key_points(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle key point extraction action."""
        text = request.payload["text"]
        max_points = request.payload.get("max_points", 5)
        prompt = (
            f"Extract the top {max_points} key points from the following text. "
            f"Present each as a concise bullet point:\n\n{text}"
        )
        return await self.process_query(prompt)

    async def process_query(
        self, request_text: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a summarization query using LLM."""
        try:
            logger.info("Summarization Agent processing: %s...", request_text[:50])
            messages = [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": request_text},
            ]
            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="chat",
                temperature=0.5,
                max_tokens=LLMDefaults.SYNTHESIS_MAX_TOKENS,
                top_p=LLMDefaults.DEFAULT_TOP_P,
            )
            response_text = self._extract_content(response)
            return {
                "status": "success",
                "response": response_text,
                "response_text": response_text,
                "agent_type": "summarization",
                "model_used": self.model_name,
                "token_usage": response.get("usage", {})
                if isinstance(response, dict)
                else {},
            }
        except Exception as e:
            logger.error("Summarization Agent error: %s", e)
            return {
                "status": "error",
                "response": "Error generating summary. Please try again.",
                "response_text": str(e),
                "agent_type": "summarization",
                "model_used": self.model_name,
            }

    def _get_system_prompt(self) -> str:
        """Get system prompt for summarization tasks."""
        return (
            "You are an expert summarization assistant. Your role is to create "
            "clear, accurate summaries that capture the essential information.\n\n"
            "Guidelines:\n"
            "- Capture the main ideas and critical details\n"
            "- Maintain factual accuracy - never fabricate information\n"
            "- Use clear, concise language\n"
            "- Preserve important numbers, dates, and proper nouns\n"
            "- For key points, prioritize by importance\n"
            "- Adapt summary length to the requested format"
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


_summarization_agent_instance = None
_summarization_agent_lock = threading.Lock()


def get_summarization_agent() -> SummarizationAgent:
    """Get the singleton Summarization Agent instance (thread-safe)."""
    global _summarization_agent_instance
    if _summarization_agent_instance is None:
        with _summarization_agent_lock:
            if _summarization_agent_instance is None:
                _summarization_agent_instance = SummarizationAgent()
    return _summarization_agent_instance
