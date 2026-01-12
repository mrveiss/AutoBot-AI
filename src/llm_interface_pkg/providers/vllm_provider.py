# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
vLLM Provider Handler - Handler for vLLM LLM requests with prefix caching.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

import logging
import time
from typing import Optional

from src.config import UnifiedConfigManager

from ..models import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)
config = UnifiedConfigManager()


class VLLMProviderHandler:
    """
    vLLM Provider Handler with prefix caching support.

    Handles vLLM-specific request formatting and initializes vLLM provider on demand.
    """

    def __init__(self):
        """Initialize vLLM provider handler."""
        self._vllm_provider = None

    async def _ensure_initialized(self, model_name: Optional[str] = None):
        """
        Initialize vLLM provider if not already initialized.

        Args:
            model_name: Model name to use for initialization
        """
        if self._vllm_provider is None:
            from src.llm_providers.vllm_provider import VLLMProvider

            model_name = model_name or config.get(
                "llm.vllm.default_model", "meta-llama/Llama-3.2-3B-Instruct"
            )

            vllm_config = {
                "model": model_name,
                "tensor_parallel_size": config.get(
                    "llm.vllm.tensor_parallel_size", 1
                ),
                "gpu_memory_utilization": config.get(
                    "llm.vllm.gpu_memory_utilization", 0.9
                ),
                "max_model_len": config.get("llm.vllm.max_model_len", 8192),
                "trust_remote_code": config.get(
                    "llm.vllm.trust_remote_code", False
                ),
                "dtype": config.get("llm.vllm.dtype", "auto"),
                "enable_chunked_prefill": config.get(
                    "llm.vllm.enable_chunked_prefill", True
                ),
            }

            self._vllm_provider = VLLMProvider(vllm_config)
            await self._vllm_provider.initialize()
            logger.info("vLLM provider initialized with model: %s", model_name)

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """
        Handle vLLM requests with prefix caching support.

        Args:
            request: LLM request object

        Returns:
            LLMResponse object
        """
        start_time = time.time()

        try:
            await self._ensure_initialized(request.model_name)

            response_data = await self._vllm_provider.chat_completion(
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens or 512,
                top_p=request.top_p,
                frequency_penalty=request.frequency_penalty,
                presence_penalty=request.presence_penalty,
                stop=request.stop,
            )

            processing_time = time.time() - start_time

            return LLMResponse(
                content=response_data["message"]["content"],
                model=response_data["model"],
                provider="vllm",
                processing_time=processing_time,
                request_id=request.request_id,
                usage=response_data.get("usage", {}),
                metadata={
                    "generation_time": response_data.get("generation_time", 0),
                    "finish_reason": response_data.get("finish_reason", "stop"),
                    "prefix_caching_enabled": True,
                },
            )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error("vLLM request failed: %s", e)
            raise

    async def cleanup(self):
        """Cleanup vLLM provider resources."""
        if self._vllm_provider is not None:
            try:
                await self._vllm_provider.cleanup()
                logger.info("vLLM provider cleaned up successfully")
            except Exception as e:
                logger.warning("Error cleaning up vLLM provider: %s", e)
            finally:
                self._vllm_provider = None


__all__ = [
    "VLLMProviderHandler",
]
