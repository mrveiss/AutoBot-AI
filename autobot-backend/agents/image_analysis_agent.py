# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Image Analysis Agent - Specialized for vision tasks and image understanding.

Handles image analysis, object detection, and scene description using
LLM-based vision capabilities. Accepts image descriptions or base64-encoded
image data for analysis.
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


class ImageAnalysisAgent(StandardizedAgent):
    """Agent specialized for image analysis and vision tasks."""

    AGENT_ID = "image_analysis"

    def __init__(self):
        """Initialize the Image Analysis Agent with LLM configuration."""
        super().__init__("image_analysis")
        self.llm_interface = LLMInterface()
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)
        self.capabilities = [
            "image_analysis",
            "object_detection",
            "scene_description",
            "image_classification",
            "visual_question_answering",
        ]
        self._register_action_handlers()
        logger.info(
            "Image Analysis Agent initialized: provider=%s, model=%s",
            self.llm_provider,
            self.model_name,
        )

    def _register_action_handlers(self):
        """Register action handlers for image analysis operations."""
        self.register_actions(
            {
                "analyze_image": ActionHandler(
                    handler_method="handle_analyze_image",
                    required_params=["image_data"],
                    optional_params=["query", "analysis_type"],
                    description="Analyze an image and provide insights",
                ),
                "describe_image": ActionHandler(
                    handler_method="handle_describe_image",
                    required_params=["image_data"],
                    optional_params=["detail_level"],
                    description="Generate a description of an image",
                ),
            }
        )

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports."""
        return self.capabilities.copy()

    async def handle_analyze_image(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle image analysis action."""
        image_data = request.payload["image_data"]
        query = request.payload.get("query", "Analyze this image in detail")
        analysis_type = request.payload.get("analysis_type", "general")
        prompt = self._build_image_prompt(image_data, query, analysis_type)
        return await self.process_query(prompt)

    async def handle_describe_image(self, request: AgentRequest) -> Dict[str, Any]:
        """Handle image description action."""
        image_data = request.payload["image_data"]
        detail_level = request.payload.get("detail_level", "detailed")
        prompt = (
            f"Provide a {detail_level} description of the following image.\n\n"
            f"Image data:\n{image_data}"
        )
        return await self.process_query(prompt)

    def _build_image_prompt(
        self, image_data: str, query: str, analysis_type: str
    ) -> str:
        """Build analysis prompt based on image data and analysis type."""
        type_instructions = {
            "objects": "Focus on identifying and listing all objects visible.",
            "scene": "Describe the overall scene, setting, and atmosphere.",
            "text": "Extract and transcribe any text visible in the image.",
            "general": "Provide a comprehensive analysis of the image content.",
        }
        instruction = type_instructions.get(analysis_type, type_instructions["general"])
        return f"{query}\n\n{instruction}\n\nImage data:\n{image_data}"

    async def process_query(
        self, request_text: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process an image analysis query using LLM."""
        try:
            logger.info("Image Analysis Agent processing: %s...", request_text[:50])
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
                "agent_type": "image_analysis",
                "model_used": self.model_name,
                "token_usage": response.get("usage", {})
                if isinstance(response, dict)
                else {},
            }
        except Exception as e:
            logger.error("Image Analysis Agent error: %s", e)
            return {
                "status": "error",
                "response": "Error analyzing image. Please try again.",
                "response_text": str(e),
                "agent_type": "image_analysis",
                "model_used": self.model_name,
            }

    def _get_system_prompt(self) -> str:
        """Get system prompt for image analysis tasks."""
        return (
            "You are an expert image analyst with strong visual understanding. "
            "Your role is to analyze images and provide detailed descriptions.\n\n"
            "Guidelines:\n"
            "- Describe visual elements systematically (foreground to background)\n"
            "- Identify objects, people, text, colors, and spatial relationships\n"
            "- Note image quality, lighting conditions, and composition\n"
            "- For object detection, list items with approximate positions\n"
            "- For scene description, capture mood and context\n"
            "- Be precise about what you observe vs. what you infer"
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


_image_analysis_agent_instance = None
_image_analysis_agent_lock = threading.Lock()


def get_image_analysis_agent() -> ImageAnalysisAgent:
    """Get the singleton Image Analysis Agent instance (thread-safe)."""
    global _image_analysis_agent_instance
    if _image_analysis_agent_instance is None:
        with _image_analysis_agent_lock:
            if _image_analysis_agent_instance is None:
                _image_analysis_agent_instance = ImageAnalysisAgent()
    return _image_analysis_agent_instance
