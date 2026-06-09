# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""
Sentiment Analysis Agent - Specialized for text sentiment and emotion classification.

Handles sentiment analysis (positive/negative/neutral) and fine-grained
emotion classification from text input.
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


class SentimentAnalysisAgent(StandardizedAgent):
    """Agent specialized for sentiment analysis and emotion classification."""

    AGENT_ID = "sentiment_analysis"

    def __init__(self):
        """Initialize the Sentiment Analysis Agent with LLM configuration."""
        super().__init__("sentiment_analysis")
        self.llm_interface = get_llm_service()
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

    async def process_query(self, request_text: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Process a sentiment analysis query using the vLLM-optimised API (Issue #3389)."""
        try:
            logger.info("Sentiment Analysis Agent processing: %s...", request_text[:50])
            session_id = (context or {}).get("session_id") or str(uuid.uuid4())
            response = await self.llm_interface.chat_optimized(
                agent_type=self.AGENT_ID,
                user_message=request_text,
                session_id=session_id,
                user_name=(context or {}).get("user_name"),
                user_role=(context or {}).get("user_role"),
                temperature=0.1,
                max_tokens=LLMDefaults.CHAT_MAX_TOKENS,
                top_p=LLMDefaults.DEFAULT_TOP_P,
            )
            response_text = self._extract_content(response)
            result = {
                "status": "success",
                "response": response_text,
                "response_text": response_text,
                "agent_type": "sentiment_analysis",
                "model_used": self.model_name,
                "token_usage": (response.get("usage", {}) if isinstance(response, dict) else {}),
            }
            diary_entry = (
                f"SESSION:{session_id}|ACTION:sentiment_analysis" f"|OUTCOME:{result['status']}|TOPIC:sentiment"
            )
            await self.memory_manager.agent_diary.write(self.AGENT_ID, session_id, diary_entry, topic="sentiment")
            return result
        except Exception as e:
            logger.error("Sentiment Analysis Agent error: %s", e)
            return {
                "status": "error",
                "response": "Error analyzing sentiment. Please try again.",
                "response_text": str(e),
                "agent_type": "sentiment_analysis",
                "model_used": self.model_name,
            }

    async def _before_process(self, context: dict) -> dict:
        """Inject cached session sentiment history into context."""
        session_id = context.get("session_id")
        if session_id:
            history = await self.memory_manager.working_memory.get(session_id, "sentiment_history")
            if history:
                context["sentiment_history"] = history
        return context

    async def _after_process(self, context: dict, result: Any) -> None:
        """Persist the most recent sentiment label to working memory."""
        if not result:
            return
        session_id = context.get("session_id")
        if not session_id:
            return
        sentiment = result.get("response", "") if isinstance(result, dict) else ""
        if sentiment:
            await self.memory_manager.working_memory.store(session_id, "sentiment_history", sentiment)

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


get_sentiment_analysis_agent = lazy_singleton(SentimentAnalysisAgent)
"""Get the singleton Sentiment Analysis Agent instance (thread-safe)."""
