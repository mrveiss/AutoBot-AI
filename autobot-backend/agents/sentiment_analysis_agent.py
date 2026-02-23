# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Sentiment Analysis Agent - Specialized for text sentiment and emotion classification.

Handles sentiment analysis (positive/negative/neutral) and fine-grained
emotion classification from text input.
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


class SentimentAnalysisAgent(StandardizedAgent):
    """Agent specialized for sentiment analysis and emotion classification."""

    AGENT_ID = "sentiment_analysis"

    def __init__(self):
        """Initialize the Sentiment Analysis Agent with LLM configuration."""
        super().__init__("sentiment_analysis")
        self.llm_interface = LLMInterface()
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)
        self.capabilities = [
            "sentiment_analysis",
            "emotion_classification",
            "opinion_mining",
            "tone_detection",
        ]
        self._register_action_handlers()
        logger.info(
            "Sentiment Analysis Agent initialized: provider=%s, model=%s",
            self.llm_provider,
            self.model_name,
        )

    def _register_action_handlers(self):
        """Register action handlers for sentiment analysis operations."""
        self.register_actions(
            {
                "analyze_sentiment": ActionHandler(
                    handler_method="handle_analyze_sentiment",
                    required_params=["text"],
                    optional_params=["granularity"],
                    description="Analyze sentiment of text",
                ),
                "classify_emotion": ActionHandler(
                    handler_method="handle_classify_emotion",
                    required_params=["text"],
                    description="Classify emotions in text",
                ),
            }
        )

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports."""
        return self.capabilities.copy()

    async def handle_analyze_sentiment(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle sentiment analysis action."""
        text = request.payload["text"]
        granularity = request.payload.get("granularity", "sentence")
        prompt = (
            f"Analyze the sentiment of the following text at {granularity} level. "
            "Respond with a JSON object containing: sentiment (positive/negative/neutral), "
            f"confidence (0-1), and explanation.\n\nText:\n{text}"
        )
        return await self.process_query(prompt)

    async def handle_classify_emotion(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle emotion classification action."""
        text = request.payload["text"]
        prompt = (
            "Classify the emotions expressed in the following text. "
            "Respond with a JSON object containing: primary_emotion, "
            "secondary_emotions (list), intensity (low/medium/high), "
            f"and explanation.\n\nText:\n{text}"
        )
        return await self.process_query(prompt)

    async def process_query(
        self, request_text: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a sentiment analysis query using LLM."""
        try:
            logger.info("Sentiment Analysis Agent processing: %s...", request_text[:50])
            messages = [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": request_text},
            ]
            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="chat",
                temperature=0.1,
                max_tokens=LLMDefaults.CHAT_MAX_TOKENS,
                top_p=LLMDefaults.DEFAULT_TOP_P,
            )
            response_text = self._extract_content(response)
            return {
                "status": "success",
                "response": response_text,
                "response_text": response_text,
                "agent_type": "sentiment_analysis",
                "model_used": self.model_name,
                "token_usage": (
                    response.get("usage", {}) if isinstance(response, dict) else {}
                ),
            }
        except Exception as e:
            logger.error("Sentiment Analysis Agent error: %s", e)
            return {
                "status": "error",
                "response": "Error analyzing sentiment. Please try again.",
                "response_text": str(e),
                "agent_type": "sentiment_analysis",
                "model_used": self.model_name,
            }

    def _get_system_prompt(self) -> str:
        """Get system prompt for sentiment analysis tasks."""
        return (
            "You are an expert in sentiment analysis and emotion detection. "
            "Your role is to accurately classify sentiment and emotions in text.\n\n"
            "Guidelines:\n"
            "- Provide structured JSON output when requested\n"
            "- Consider context, sarcasm, and implicit sentiment\n"
            "- Distinguish between author sentiment and reported sentiment\n"
            "- For mixed sentiment, identify dominant and secondary sentiments\n"
            "- Include confidence scores for classifications\n"
            "- Handle multi-language text when encountered"
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


_sentiment_analysis_agent_instance = None
_sentiment_analysis_agent_lock = threading.Lock()


def get_sentiment_analysis_agent() -> SentimentAnalysisAgent:
    """Get the singleton Sentiment Analysis Agent instance (thread-safe)."""
    global _sentiment_analysis_agent_instance
    if _sentiment_analysis_agent_instance is None:
        with _sentiment_analysis_agent_lock:
            if _sentiment_analysis_agent_instance is None:
                _sentiment_analysis_agent_instance = SentimentAnalysisAgent()
    return _sentiment_analysis_agent_instance
