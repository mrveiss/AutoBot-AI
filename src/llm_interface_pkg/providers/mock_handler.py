# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Mock and Local Handlers - Handlers for mock and local LLM requests.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

import asyncio
import logging
import time

from ..models import LLMRequest, LLMResponse
from ..mock_providers import local_llm

logger = logging.getLogger(__name__)


class MockHandler:
    """
    Mock LLM Handler for testing purposes.

    Provides simulated LLM responses for testing without actual API calls.
    """

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """
        Handle mock requests for testing.

        Args:
            request: LLM request object

        Returns:
            LLMResponse with mock content
        """
        start_time = time.time()
        await asyncio.sleep(0.1)  # Simulate processing

        processing_time = time.time() - start_time

        return LLMResponse(
            content=f"Mock response to: {request.messages[-1]['content'][:50]}...",
            model="mock-model",
            provider="mock",
            processing_time=processing_time,
            request_id=request.request_id,
        )


class LocalHandler:
    """
    Local LLM Handler for TinyLLaMA fallback.

    Handles local LLM requests using the TinyLLaMA model.
    """

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """
        Handle local LLM requests.

        Args:
            request: LLM request object

        Returns:
            LLMResponse from local model
        """
        start_time = time.time()

        response = await local_llm.generate(
            "\n".join(
                [f"{m['role']}: {m['content']}" for m in request.messages]
            )
        )

        processing_time = time.time() - start_time

        return LLMResponse(
            content=response["choices"][0]["message"]["content"],
            model="local-tinyllama",
            provider="local",
            processing_time=processing_time,
            request_id=request.request_id,
        )


__all__ = [
    "MockHandler",
    "LocalHandler",
]
