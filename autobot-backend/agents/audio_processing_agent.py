# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Audio Processing Agent - Specialized for audio transcription and analysis.

Handles audio content analysis, transcription processing, and audio metadata
interpretation using LLM capabilities.
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


class AudioProcessingAgent(StandardizedAgent):
    """Agent specialized for audio transcription and analysis."""

    AGENT_ID = "audio_processing"

    def __init__(self):
        """Initialize the Audio Processing Agent with LLM configuration."""
        super().__init__("audio_processing")
        self.llm_interface = LLMInterface()
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)
        self.capabilities = [
            "audio_transcription",
            "audio_analysis",
            "speech_processing",
            "audio_summarization",
        ]
        self._register_action_handlers()
        logger.info(
            "Audio Processing Agent initialized: provider=%s, model=%s",
            self.llm_provider,
            self.model_name,
        )

    def _register_action_handlers(self):
        """Register action handlers for audio processing operations."""
        self.register_actions(
            {
                "transcribe": ActionHandler(
                    handler_method="handle_transcribe",
                    required_params=["audio_data"],
                    optional_params=["language", "format"],
                    description="Transcribe audio content",
                ),
                "analyze_audio": ActionHandler(
                    handler_method="handle_analyze_audio",
                    required_params=["audio_data"],
                    optional_params=["analysis_type"],
                    description="Analyze audio content and metadata",
                ),
            }
        )

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports."""
        return self.capabilities.copy()

    async def handle_transcribe(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle audio transcription action."""
        audio_data = request.payload["audio_data"]
        language = request.payload.get("language", "auto-detect")
        output_format = request.payload.get("format", "text")
        prompt = (
            f"Process the following audio data for transcription (language: {language}, "
            f"output format: {output_format}).\n\nAudio data:\n{audio_data}"
        )
        return await self.process_query(prompt)

    async def handle_analyze_audio(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle audio analysis action."""
        audio_data = request.payload["audio_data"]
        analysis_type = request.payload.get("analysis_type", "general")
        prompt = (
            f"Analyze the following audio content ({analysis_type} analysis). "
            "Identify key characteristics including speaker information, "
            f"content type, and quality assessment.\n\nAudio data:\n{audio_data}"
        )
        return await self.process_query(prompt)

    async def process_query(
        self, request_text: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process an audio processing query using LLM."""
        try:
            logger.info("Audio Processing Agent processing: %s...", request_text[:50])
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
                "agent_type": "audio_processing",
                "model_used": self.model_name,
                "token_usage": response.get("usage", {})
                if isinstance(response, dict)
                else {},
            }
        except Exception as e:
            logger.error("Audio Processing Agent error: %s", e)
            return {
                "status": "error",
                "response": "Error processing audio. Please try again.",
                "response_text": str(e),
                "agent_type": "audio_processing",
                "model_used": self.model_name,
            }

    def _get_system_prompt(self) -> str:
        """Get system prompt for audio processing tasks."""
        return (
            "You are an expert audio processing assistant. Your role is to analyze "
            "audio content, process transcriptions, and provide audio insights.\n\n"
            "Guidelines:\n"
            "- For transcription, produce accurate text with proper punctuation\n"
            "- Include speaker identification when multiple speakers are present\n"
            "- Note audio quality issues that may affect accuracy\n"
            "- For analysis, identify content type (speech, music, ambient)\n"
            "- Provide timestamps for key segments when applicable\n"
            "- Handle multiple languages and accents appropriately"
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


_audio_processing_agent_instance = None
_audio_processing_agent_lock = threading.Lock()


def get_audio_processing_agent() -> AudioProcessingAgent:
    """Get the singleton Audio Processing Agent instance (thread-safe)."""
    global _audio_processing_agent_instance
    if _audio_processing_agent_instance is None:
        with _audio_processing_agent_lock:
            if _audio_processing_agent_instance is None:
                _audio_processing_agent_instance = AudioProcessingAgent()
    return _audio_processing_agent_instance
