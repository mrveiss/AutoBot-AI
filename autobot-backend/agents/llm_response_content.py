# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Text extraction from the several LLM response shapes, split out of ``knowledge_retrieval_agent.py`` (#16665)."""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def try_extract_message_content(response: Dict) -> str | None:
    """Try to extract content from message dict (Issue #334 - extracted helper)."""
    if "message" not in response or not isinstance(response["message"], dict):
        return None
    content = response["message"].get("content")
    return content.strip() if content else None


def try_extract_choices_content(response: Dict) -> str | None:
    """Try to extract content from choices list (Issue #334 - extracted helper)."""
    if "choices" not in response or not isinstance(response["choices"], list):
        return None
    if not response["choices"]:
        return None
    choice = response["choices"][0]
    if "message" not in choice or "content" not in choice["message"]:
        return None
    return choice["message"]["content"].strip()


def extract_response_content(response: Any) -> str:
    """Extract text content from LLM response."""
    try:
        # LLMService.chat() returns an LLMResponse object, not a dict (#19649).
        object_content = getattr(response, "content", None)
        if isinstance(object_content, str):
            return object_content.strip()

        if isinstance(response, dict):
            content = try_extract_message_content(response)
            if content:
                return content
            content = try_extract_choices_content(response)
            if content:
                return content
            if "content" in response:
                return response["content"].strip()

        if isinstance(response, str):
            return response.strip()

        return str(response)

    except Exception as e:
        logger.error("Error extracting response content: %s", e)
        return "Error processing response"
