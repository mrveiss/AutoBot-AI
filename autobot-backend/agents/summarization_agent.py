# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""
Summarization Agent - Specialized for document and text summarization.

Handles text summarization with configurable length, key point extraction,
and structured summary generation.
"""

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import (
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)
from constants.threshold_constants import LLMDefaults
from services.llm_service import get_llm_service

from .base_agent import AgentRequest
from .base_modality_agent import BaseModalityAgent
from .standardized_agent import ActionHandler

# Copyright (c) 2025 mrveiss
# Author: mrveiss


logger = get_logger(__name__)


class SummarizationAgent(BaseModalityAgent):
    """Agent specialized for document and text summarization."""

    AGENT_ID = "summarization"
    QUERY_TEMPERATURE = 0.5
    QUERY_MAX_TOKENS = LLMDefaults.SYNTHESIS_MAX_TOKENS
    QUERY_ERROR_MESSAGE = "Error generating summary. Please try again."
    _LOGGER = logger

    def __init__(self):
        """Initialize the Summarization Agent with LLM configuration."""
        super().__init__("summarization")
        self.llm_interface = get_llm_service()
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


get_summarization_agent = lazy_singleton(SummarizationAgent)
"""Get the singleton Summarization Agent instance (thread-safe)."""
