# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Local LLM Providers - Local Ollama integration with mock fallback for testing.

Provides real Ollama integration when available, falls back to mock responses
only when Ollama is not configured (for testing/development without Ollama).

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
Updated in Issue #453 to use real Ollama integration.
"""

import asyncio

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.threshold_constants import TimingConstants
from constants.ttl_constants import TIMEOUT_HTTP_LONG

logger = get_logger(__name__)


class LocalLLM:
    """Local LLM provider using Ollama when available.

    Attempts to use real Ollama for text generation. Falls back to mock
    responses only when Ollama is not configured (AUTOBOT_OLLAMA_ENDPOINT not set).
    """

    def __init__(self):
        """Initialize local LLM with Ollama connection check."""
        self._ollama_url: str | None = config.ollama_url or None
        self._ollama_available = bool(self._ollama_url)
        self._default_model = config.default_llm_model

        if self._ollama_available:
            logger.info("LocalLLM initialized with Ollama at %s", self._ollama_url)
        else:
            # #10726: Raised to WARNING — a missing AUTOBOT_OLLAMA_ENDPOINT means the
            # 'local' provider silently serves mock text, masking a prod misconfiguration.
            logger.warning(
                "LocalLLM (Ollama) not configured — AUTOBOT_OLLAMA_ENDPOINT is unset or empty. "
                "The 'local' provider will return MOCK responses until Ollama is configured. "
                "Other providers (OpenAI, Anthropic, Google) work independently. "
                "Set AUTOBOT_OLLAMA_ENDPOINT in .env to enable real local inference."
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
                        "content": ("[Mock Response - Ollama not configured] " f"Prompt received: {prompt[:100]}...")
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

    async def generate(self, prompt: str, model: str | None = None) -> dict:
        """Generate response using local Ollama model.

        Falls back to mock response if Ollama is not available.

        Args:
            prompt: Input text prompt
            model: Optional model name override

        Returns:
            Dict with response in OpenAI-compatible format
        """
        if not self._ollama_available:
            # #10726: WARNING so each mock-response generation is observable in prod logs.
            logger.warning(
                "LocalLLM.generate called but Ollama is not configured — returning MOCK response. "
                "Set AUTOBOT_OLLAMA_ENDPOINT to route to a real model."
            )
            await asyncio.sleep(TimingConstants.MICRO_DELAY)
            return self._create_mock_response(prompt)

        try:
            import aiohttp

            data = {
                "model": model or self._default_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }

            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=TIMEOUT_HTTP_LONG)
                async with session.post(f"{self._ollama_url}/api/chat", json=data, timeout=timeout) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(
                            "Ollama request failed: HTTP %s - %s",
                            response.status,
                            error_text,
                        )
                        return self._create_error_response(f"Error: Ollama returned HTTP {response.status}")
                    result = await response.json()

            return self._format_ollama_response(result)

        except Exception as e:
            logger.error("Ollama request failed: %s", e)
            return self._create_error_response(f"Error: Local LLM request failed - {str(e)}")


class MockPalm:
    """Mock Palm API - for testing only.

    NOTE: This class exists only for backward compatibility and testing.
    In production, use real Google AI APIs via the appropriate provider.
    """

    class QuotaExceededError(Exception):
        """Exception raised when API quota is exceeded."""

    # #10726: MockPalm is instantiated unconditionally at module load (the module-level
    # ``palm`` global below), so a warning in __init__ would fire on every import and be
    # pure noise. The actionable signal is when the mock is actually *used* on a request
    # path — so the warning lives in the methods (get_quota_status / generate_text) instead.
    _mock_use_warned = False

    def __init__(self):
        """Initialize MockPalm (a no-op mock stub; see class note and _warn_mock_use)."""

    @classmethod
    def _warn_mock_use(cls) -> None:
        """Warn once per process when MockPalm is actually exercised on a request path."""
        if cls._mock_use_warned:
            return
        cls._mock_use_warned = True
        logger.warning(
            "MockPalm is being USED to serve a request — this is a MOCK stub with no real "
            "Google AI calls and exists for backward compatibility only. "
            "Configure GOOGLE_API_KEY and use a real Vertex/Gemini provider for production."
        )

    async def get_quota_status(self):
        """
        Get mock quota status (for testing).

        Returns:
            MockQuotaStatus with simulated quota information
        """
        self._warn_mock_use()
        await asyncio.sleep(TimingConstants.STREAMING_CHUNK_DELAY)

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
        self._warn_mock_use()
        await asyncio.sleep(TimingConstants.MICRO_DELAY)

        prompt = kwargs.get("prompt", "")
        return {
            "choices": [
                {"message": {"content": (f"[Mock Palm Response - Testing Only] " f"Prompt: {prompt[:50]}...")}}
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
