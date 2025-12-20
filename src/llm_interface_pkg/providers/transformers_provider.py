# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Transformers Provider - Handler for local Transformers LLM requests.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

import logging
import time

from ..models import LLMRequest, LLMResponse
from ..mock_providers import local_llm

logger = logging.getLogger(__name__)


class TransformersProvider:
    """
    Transformers LLM Provider for local model inference.

    Handles local model requests using the Transformers library.
    """

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """
        Enhanced Transformers chat completion with local model support.

        Args:
            request: LLM request object

        Returns:
            LLMResponse object
        """
        start_time = time.time()

        try:
            # Use local LLM fallback for now
            response = await local_llm.generate(
                "\n".join(
                    [f"{m['role']}: {m['content']}" for m in request.messages]
                )
            )

            processing_time = time.time() - start_time

            return LLMResponse(
                content=response["choices"][0]["message"]["content"],
                model=request.model_name or "local-transformers",
                provider="transformers",
                processing_time=processing_time,
                request_id=request.request_id,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error("Transformers completion error: %s", e)
            raise


__all__ = [
    "TransformersProvider",
]
