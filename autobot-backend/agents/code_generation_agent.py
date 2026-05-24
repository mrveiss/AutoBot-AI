# AutoBot - AI-Powered Automation Platform
"""
Code Generation Agent - Specialized for programming assistance and code generation.

Handles code generation from natural language descriptions, code explanation,
and multi-language programming support.
"""

import uuid
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
from .standardized_agent import ActionHandler, StandardizedAgent

# Copyright (c) 2025 mrveiss
# Author: mrveiss




logger = get_logger(__name__)


class CodeGenerationAgent(StandardizedAgent):
    """Agent specialized for code generation and programming assistance."""

    AGENT_ID = "code_generation"

    def __init__(self):
        """Initialize the Code Generation Agent with LLM configuration."""
        super().__init__("code_generation")
        self.llm_interface = get_llm_service()
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)
        self.capabilities = [
            "code_generation",
            "code_explanation",
            "code_review",
            "multi_language_support",
            "algorithm_design",
        ]
        self._register_action_handlers()
        logger.info(
            "Code Generation Agent initialized: provider=%s, model=%s",
            self.llm_provider,
            self.model_name,
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

    async def process_query(self, request_text: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Process a code generation query using the vLLM-optimised API (Issue #3389)."""
        try:
            logger.info("Code Generation Agent processing: %s...", request_text[:50])
            session_id = (context or {}).get("session_id") or str(uuid.uuid4())
            response = await self.llm_interface.chat_optimized(
                agent_type=self.AGENT_ID,
                user_message=request_text,
                session_id=session_id,
                user_name=(context or {}).get("user_name"),
                user_role=(context or {}).get("user_role"),
                temperature=0.2,
                max_tokens=LLMDefaults.EXTENDED_MAX_TOKENS,
                top_p=LLMDefaults.DEFAULT_TOP_P,
            )
            response_text = self._extract_content(response)
            return {
                "status": "success",
                "response": response_text,
                "response_text": response_text,
                "agent_type": "code_generation",
                "model_used": self.model_name,
                "token_usage": (response.get("usage", {}) if isinstance(response, dict) else {}),
            }
        except Exception as e:
            logger.error("Code Generation Agent error: %s", e)
            return {
                "status": "error",
                "response": "Error generating code. Please try rephrasing your request.",
                "response_text": str(e),
                "agent_type": "code_generation",
                "model_used": self.model_name,
            }

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


get_code_generation_agent = lazy_singleton(CodeGenerationAgent)
"""Get the singleton Code Generation Agent instance (thread-safe)."""
