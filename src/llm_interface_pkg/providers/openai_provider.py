# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
OpenAI Provider - Handler for OpenAI LLM requests.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

import logging
import time
from typing import Optional

from src.circuit_breaker import circuit_breaker_async

from ..models import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """
    OpenAI LLM Provider with circuit breaker protection.

    Handles all OpenAI-specific request formatting and response parsing.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
        """
        self.api_key = api_key

    @circuit_breaker_async("openai_service")
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """
        Enhanced OpenAI chat completion.

        Args:
            request: LLM request object

        Returns:
            LLMResponse object

        Raises:
            ValueError: If API key is not configured
        """
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")

        import openai

        client = openai.AsyncOpenAI(api_key=self.api_key)

        start_time = time.time()

        try:
            response = await client.chat.completions.create(
                model=request.model_name or "gpt-3.5-turbo",
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )

            processing_time = time.time() - start_time

            return LLMResponse(
                content=response.choices[0].message.content,
                model=response.model,
                provider="openai",
                processing_time=processing_time,
                request_id=request.request_id,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error("OpenAI completion error: %s", e)
            raise


__all__ = [
    "OpenAIProvider",
]
