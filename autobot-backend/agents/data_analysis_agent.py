# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Data Analysis Agent - Specialized for data analysis, statistics, and pattern detection.

Handles data analysis tasks using LLM to identify patterns, compute statistics,
and provide insights from structured and unstructured data.
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


class DataAnalysisAgent(StandardizedAgent):
    """Agent specialized for data analysis, statistics, and pattern detection."""

    AGENT_ID = "data_analysis"

    def __init__(self):
        """Initialize the Data Analysis Agent with LLM configuration."""
        super().__init__("data_analysis")
        self.llm_interface = LLMInterface()
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)
        self.capabilities = [
            "data_analysis",
            "statistical_analysis",
            "pattern_detection",
            "trend_identification",
            "data_summarization",
        ]
        self._register_action_handlers()
        logger.info(
            "Data Analysis Agent initialized: provider=%s, model=%s",
            self.llm_provider,
            self.model_name,
        )

    def _register_action_handlers(self):
        """Register action handlers for data analysis operations."""
        self.register_actions(
            {
                "analyze": ActionHandler(
                    handler_method="handle_analyze",
                    required_params=["data"],
                    optional_params=["query", "context"],
                    description="Analyze data and provide insights",
                ),
                "detect_patterns": ActionHandler(
                    handler_method="handle_detect_patterns",
                    required_params=["data"],
                    optional_params=["pattern_type"],
                    description="Detect patterns in data",
                ),
            }
        )

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports."""
        return self.capabilities.copy()

    async def handle_analyze(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle data analysis action."""
        data = request.payload["data"]
        query = request.payload.get("query", "Analyze this data and provide insights")
        return await self.process_query(f"{query}\n\nData:\n{data}")

    async def handle_detect_patterns(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle pattern detection action."""
        data = request.payload["data"]
        pattern_type = request.payload.get("pattern_type", "any")
        prompt = f"Detect {pattern_type} patterns in the following data:\n\n{data}"
        return await self.process_query(prompt)

    async def process_query(
        self, request_text: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a data analysis query using LLM."""
        try:
            logger.info("Data Analysis Agent processing: %s...", request_text[:50])
            messages = [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": request_text},
            ]
            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="chat",
                temperature=0.3,
                max_tokens=LLMDefaults.SYNTHESIS_MAX_TOKENS,
                top_p=LLMDefaults.DEFAULT_TOP_P,
            )
            response_text = self._extract_content(response)
            return {
                "status": "success",
                "response": response_text,
                "response_text": response_text,
                "agent_type": "data_analysis",
                "model_used": self.model_name,
                "token_usage": response.get("usage", {})
                if isinstance(response, dict)
                else {},
            }
        except Exception as e:
            logger.error("Data Analysis Agent error: %s", e)
            return {
                "status": "error",
                "response": "Error analyzing data. Please try rephrasing your request.",
                "response_text": str(e),
                "agent_type": "data_analysis",
                "model_used": self.model_name,
            }

    def _get_system_prompt(self) -> str:
        """Get system prompt for data analysis tasks."""
        return (
            "You are an expert data analyst. Your role is to analyze data, identify "
            "patterns, compute statistics, and provide actionable insights.\n\n"
            "Guidelines:\n"
            "- Present findings in a clear, structured format\n"
            "- Include relevant statistics and metrics when applicable\n"
            "- Identify trends, anomalies, and correlations\n"
            "- Provide actionable recommendations based on the analysis\n"
            "- Use tables or bullet points for clarity when appropriate\n"
            "- If data is insufficient, state what additional data would help"
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


_data_analysis_agent_instance = None
_data_analysis_agent_lock = threading.Lock()


def get_data_analysis_agent() -> DataAnalysisAgent:
    """Get the singleton Data Analysis Agent instance (thread-safe)."""
    global _data_analysis_agent_instance
    if _data_analysis_agent_instance is None:
        with _data_analysis_agent_lock:
            if _data_analysis_agent_instance is None:
                _data_analysis_agent_instance = DataAnalysisAgent()
    return _data_analysis_agent_instance
