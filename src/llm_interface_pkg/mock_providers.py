# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Mock LLM Providers - Local fallback and mock implementations for testing.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

import asyncio
import random
import logging

logger = logging.getLogger(__name__)


class LocalLLM:
    """Local TinyLLaMA fallback"""

    async def generate(self, prompt: str) -> dict:
        """
        Generate response using local TinyLLaMA fallback model.

        Args:
            prompt: Input text prompt

        Returns:
            Dict with response in OpenAI-compatible format
        """
        logger.info("Using local TinyLLaMA fallback.")
        await asyncio.sleep(0.1)
        return {
            "choices": [
                {"message": {"content": f"Local TinyLLaMA response to: {prompt}"}}
            ]
        }


class MockPalm:
    """Mock Palm API for testing"""

    class QuotaExceededError(Exception):
        """Exception raised when API quota is exceeded."""

        pass

    async def get_quota_status(self):
        """
        Get current API quota status (mock implementation for testing).

        Returns:
            Dict with quota usage information
        """
        await asyncio.sleep(0.05)

        class MockQuotaStatus:
            def __init__(self, remaining_tokens):
                """Initialize mock quota status with remaining token count."""
                self.remaining_tokens = remaining_tokens

        mock_status = MockQuotaStatus(50000)
        if random.random() < 0.2:
            mock_status.remaining_tokens = 500
        return mock_status

    async def generate_text(self, **kwargs):
        """
        Generate text using mock Palm API (for testing).

        Args:
            **kwargs: Generation parameters

        Returns:
            Dict with generated text

        Raises:
            QuotaExceededError: Randomly raised to test quota handling
        """
        await asyncio.sleep(0.1)

        if random.random() < 0.1:
            raise self.QuotaExceededError("Mock Quota Exceeded")
        return {
            "choices": [
                {
                    "message": {
                        "content": f"Google LLM response to: {kwargs.get('prompt')}"
                    }
                }
            ]
        }


# Global instances for backward compatibility
local_llm = LocalLLM()
palm = MockPalm()


__all__ = [
    "LocalLLM",
    "MockPalm",
    "local_llm",
    "palm",
]
