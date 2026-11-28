# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""
Code Generation Agent - Specialized for programming assistance and code generation.

Handles code generation from natural language descriptions, code explanation,
and multi-language programming support.
"""

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from constants.threshold_constants import LLMDefaults

from .base_agent import AgentRequest
from .base_modality_agent import BaseModalityAgent
from .standardized_agent import ActionHandler

# Copyright (c) 2025 mrveiss
# Author: mrveiss


logger = get_logger(__name__)


class CodeGenerationAgent(BaseModalityAgent):
    """Agent specialized for code generation and programming assistance."""

    AGENT_ID = "code_generation"
    QUERY_TEMPERATURE = 0.2
    QUERY_MAX_TOKENS = LLMDefaults.EXTENDED_MAX_TOKENS
    QUERY_ERROR_MESSAGE = "Error generating code. Please try rephrasing your request."
    _LOGGER = logger
    CAPABILITIES = (
        "code_generation",
        "code_explanation",
        "code_review",
        "multi_language_support",
        "algorithm_design",
    )

    def _register_action_handlers(self):
        """Register action handlers for code generation operations."""
        self.register_actions(
            {
                "generate": ActionHandler(
                    handler_method="handle_generate",
                    required_params=["description"],
                    optional_params=["language", "context"],
                    description="Generate code from description",
                ),
                "explain": ActionHandler(
                    handler_method="handle_explain",
                    required_params=["code"],
                    optional_params=["detail_level"],
                    description="Explain existing code",
                ),
            }
        )

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports."""
        return self.capabilities.copy()

    async def handle_generate(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle code generation action."""
        description = request.payload["description"]
        language = request.payload.get("language", "Python")
        prompt = f"Generate {language} code for: {description}"
        return await self.process_query(prompt)

    async def handle_explain(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle code explanation action."""
        code = request.payload["code"]
        detail_level = request.payload.get("detail_level", "detailed")
        prompt = f"Explain the following code ({detail_level} explanation):\n\n```\n{code}\n```"
        return await self.process_query(prompt)

    def _get_system_prompt(self) -> str:
        """Get system prompt for code generation tasks."""
        return (
            "You are an expert programmer and code generation assistant. "
            "Your role is to write clean, efficient, well-documented code.\n\n"
            "Guidelines:\n"
            "- Write production-quality code with proper error handling\n"
            "- Include clear comments explaining complex logic\n"
            "- Follow language-specific best practices and conventions\n"
            "- Use descriptive variable and function names\n"
            "- Consider edge cases and input validation\n"
            "- When explaining code, break it down step by step"
        )


get_code_generation_agent = lazy_singleton(CodeGenerationAgent)
"""Get the singleton Code Generation Agent instance (thread-safe)."""
