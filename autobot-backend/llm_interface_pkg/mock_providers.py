# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Local LLM Providers - Local Ollama integration with mock fallback for testing.

Provides real Ollama integration when available, falls back to mock responses
only when Ollama is not configured (for testing/development without Ollama).

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
Updated in Issue #453 to use real Ollama integration.
"""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class LocalLLM:
    """Local LLM provider using Ollama when available.

    Attempts to use real Ollama for text generation. Falls back to mock
    responses only when Ollama is not configured (AUTOBOT_OLLAMA_HOST/PORT not set).
    """

    def __init__(self):
        """Initialize local LLM with Ollama connection check."""
        self._ollama_host = os.getenv("AUTOBOT_OLLAMA_HOST")
        self._ollama_port = os.getenv("AUTOBOT_OLLAMA_PORT")
        self._ollama_available = bool(self._ollama_host and self._ollama_port)
        self._ollama_url: Optional[str] = None
        self._default_model = os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", "llama3.2")

        if self._ollama_available:
            self._ollama_url = f"http://{self._ollama_host}:{self._ollama_port}"
            logger.info("LocalLLM initialized with Ollama at %s", self._ollama_url)
        else:
            # Issue #665: More informative warning - LocalLLM is optional
            logger.debug(
                "LocalLLM (Ollama) not configured - this provider will use mock responses. "
                "This only affects the 'local' LLM provider. Other providers (OpenAI, Anthropic, "
                "Google) work independently. To enable local Ollama: set AUTOBOT_OLLAMA_HOST "
                "and AUTOBOT_OLLAMA_PORT in .env file."
            )

    def _create_mock_response(self, prompt: str) -> dict:
        """Issue #665: Extracted from generate to reduce function length.

        Create a mock response when Ollama is not configured.

        Args:
            prompt: Input text prompt

        Returns:
            Dict with mock response in OpenAI-compatible format
        """
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "[Mock Response - Ollama not configured] "
                            f"Prompt received: {prompt[:100]}..."
                        )
                    }
                }
            ],
            "_mock": True,
        }

    def _create_error_response(self, error_message: str) -> dict:
        """Issue #665: Extracted from generate to reduce function length.

        Create an error response dict.

        Args:
            error_message: Error message to include

        Returns:
            Dict with error response in OpenAI-compatible format
        """
        return {
            "choices": [{"message": {"content": error_message}}],
            "_error": True,
        }

    def _format_ollama_response(self, result: dict) -> dict:
        """Issue #665: Extracted from generate to reduce function length.

        Format Ollama API result into OpenAI-compatible response.

        Args:
            result: Raw Ollama API response

        Returns:
            Dict with response in OpenAI-compatible format
        """
        content = result.get("message", {}).get("content", "")
        logger.debug("Ollama response received: %d chars", len(content))
        return {
            "choices": [{"message": {"content": content}}],
            "model": result.get("model"),
            "usage": {
                "prompt_tokens": result.get("prompt_eval_count", 0),
                "completion_tokens": result.get("eval_count", 0),
            },
        }

    async def generate(self, prompt: str, model: Optional[str] = None) -> dict:
        """Generate response using local Ollama model.

        Falls back to mock response if Ollama is not available.

        Args:
            prompt: Input text prompt
            model: Optional model name override

        Returns:
            Dict with response in OpenAI-compatible format
        """
        if not self._ollama_available:
            logger.debug("Using mock response (Ollama not configured)")
            await asyncio.sleep(0.1)
            return self._create_mock_response(prompt)

        try:
            import aiohttp

            data = {
                "model": model or self._default_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }

            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=120.0)
                async with session.post(
                    f"{self._ollama_url}/api/chat", json=data, timeout=timeout
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(
                            "Ollama request failed: HTTP %s - %s",
                            response.status,
                            error_text,
                        )
                        return self._create_error_response(
                            f"Error: Ollama returned HTTP {response.status}"
                        )
                    result = await response.json()

            return self._format_ollama_response(result)

        except Exception as e:
            logger.error("Ollama request failed: %s", e)
            return self._create_error_response(
                f"Error: Local LLM request failed - {str(e)}"
            )


class MockPalm:
    """Mock Palm API - for testing only.

    NOTE: This class exists only for backward compatibility and testing.
    In production, use real Google AI APIs via the appropriate provider.
    """

    class QuotaExceededError(Exception):
        """Exception raised when API quota is exceeded."""

    def __init__(self):
        """Initialize MockPalm with debug message about mock usage."""
        # Issue #665: Changed to debug - MockPalm is a fallback, not an error condition
        logger.debug(
            "MockPalm provider instantiated (mock fallback). "
            "For real Google AI, configure GOOGLE_API_KEY in .env file."
        )

    async def get_quota_status(self):
        """
        Get mock quota status (for testing).

        Returns:
            MockQuotaStatus with simulated quota information
        """
        await asyncio.sleep(0.05)

        class MockQuotaStatus:
            def __init__(self, remaining_tokens):
                """Initialize mock quota status with remaining token count."""
                self.remaining_tokens = remaining_tokens

        # Always return healthy quota for testing
        return MockQuotaStatus(50000)

    async def generate_text(self, **kwargs):
        """
        Generate mock text response (for testing).

        Args:
            **kwargs: Generation parameters

        Returns:
            Dict with mock generated text
        """
        await asyncio.sleep(0.1)

        prompt = kwargs.get("prompt", "")
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            f"[Mock Palm Response - Testing Only] "
                            f"Prompt: {prompt[:50]}..."
                        )
                    }
                }
            ],
            "_mock": True,
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
