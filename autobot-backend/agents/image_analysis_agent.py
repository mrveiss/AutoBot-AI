# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""
Image Analysis Agent - Specialized for vision tasks and image understanding.

Handles image analysis, object detection, and scene description using
LLM-based vision capabilities. Accepts image descriptions or base64-encoded
image data for analysis.
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


class ImageAnalysisAgent(BaseModalityAgent):
    """Agent specialized for image analysis and vision tasks."""

    AGENT_ID = "image_analysis"
    QUERY_TEMPERATURE = 0.5
    QUERY_MAX_TOKENS = LLMDefaults.SYNTHESIS_MAX_TOKENS
    QUERY_ERROR_MESSAGE = "Error analyzing image. Please try again."
    _LOGGER = logger

    def __init__(self):
        """Initialize the Image Analysis Agent with LLM configuration."""
        super().__init__("image_analysis")
        self.llm_interface = get_llm_service()
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
        prompt = f"Provide a {detail_level} description of the following image.\n\n" f"Image data:\n{image_data}"
        return await self.process_query(prompt)

    def _build_image_prompt(self, image_data: str, query: str, analysis_type: str) -> str:
        """Build analysis prompt based on image data and analysis type."""
        type_instructions = {
            "objects": "Focus on identifying and listing all objects visible.",
            "scene": "Describe the overall scene, setting, and atmosphere.",
            "text": "Extract and transcribe any text visible in the image.",
            "general": "Provide a comprehensive analysis of the image content.",
        }
        instruction = type_instructions.get(analysis_type, type_instructions["general"])
        return f"{query}\n\n{instruction}\n\nImage data:\n{image_data}"

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


get_image_analysis_agent = lazy_singleton(ImageAnalysisAgent)
