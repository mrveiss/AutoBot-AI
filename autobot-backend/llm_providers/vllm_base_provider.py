# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
vLLM Base Provider - Wraps vLLM in BaseProvider interface for registry integration.

Issue #4341: Model Provider Flexibility & Vendor-Agnostic Switching

This wrapper adapts the vLLMProvider to the standardized BaseProvider interface,
enabling vLLM models to participate in fallback chains, health checks, and
runtime provider switching without code changes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from llm_interface_pkg.models import LLMRequest, LLMResponse
from llm_interface_pkg.types import ProviderType

from .base_provider import BaseProvider
from .vllm_provider import VLLMProvider

logger = logging.getLogger(__name__)


class VLLMBaseProvider(BaseProvider):
    """
    Standardized BaseProvider wrapper for vLLM.

    Wraps the existing VLLMProvider (which handles model loading and inference)
    and adapts it to the BaseProvider interface for integration with the
    provider registry, fallback chains, and health monitoring.

    Provider name: "vllm"
    """

    provider_name = ProviderType.VLLM.value

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the vLLM wrapper.

        Args:
            settings: Configuration dict passed to VLLMProvider.
                     Must include "model" key with HuggingFace model path.
                     See VLLMProvider for full list of options.

        Raises:
            ImportError: If vLLM is not installed.
            ValueError: If "model" is not in settings.
        """
        super().__init__(settings)
        if not self.settings or "model" not in self.settings:
            raise ValueError('VLLMBaseProvider requires "model" in settings')

        self._vllm_provider: Optional[VLLMProvider] = None
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def _ensure_initialized(self) -> None:
        """Lazily initialize the underlying VLLMProvider."""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            try:
                self._vllm_provider = VLLMProvider(self.settings)
                await self._vllm_provider.initialize()
                self._initialized = True
                logger.info("vLLM provider initialized for model: %s", self.settings.get("model"))
            except Exception as exc:
                logger.error("Failed to initialize vLLM provider: %s", exc)
                raise

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """
        Execute a chat completion request via vLLM.

        Args:
            request: Standardized LLM request.

        Returns:
            LLMResponse with content populated or error field set.
        """
        try:
            self._total_requests += 1
            await self._ensure_initialized()

            # Convert LLMRequest to vLLM format
            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

            # Extract inference parameters from request metadata
            # Issue #4524: only apply chat_template when explicitly set — never default
            # to DEFAULT_TEMPLATE, as models with native tokenizer templates would
            # receive double-templated prompts.
            api_kwargs = request.metadata.get("api_kwargs", {})
            chat_template = request.metadata.get("chat_template")
            inference_kwargs = {
                "temperature": api_kwargs.get("temperature", 0.7),
                "max_tokens": api_kwargs.get("max_tokens", 512),
                "top_p": api_kwargs.get("top_p", 0.95),
                "top_k": api_kwargs.get("top_k", -1),
                "frequency_penalty": api_kwargs.get("frequency_penalty", 0.0),
                "presence_penalty": api_kwargs.get("presence_penalty", 0.0),
                "stop": api_kwargs.get("stop", None),
            }
            if chat_template:
                inference_kwargs["chat_template"] = chat_template

            # Run inference in executor to avoid blocking
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                self._vllm_provider.chat_completion,
                messages,
                inference_kwargs,
            )

            # Adapt vLLM response to LLMResponse
            # Issue #4527: LLMResponse fields are `model` and `provider`, not model_name/provider_name
            return LLMResponse(
                content=response["message"]["content"],
                model=response.get("model", request.model_name or "vllm-model"),
                provider=self.provider_name,
                usage=response.get("usage", {}),
                provider_metadata=self._build_provider_metadata(
                    model_api_name=response.get("model", request.model_name or ""),
                    api_kwargs_applied=inference_kwargs,
                    total_tokens=response.get("usage", {}).get("total_tokens"),
                ),
            )

        except Exception as exc:
            self._total_errors += 1
            logger.error("vLLM chat completion failed: %s", exc)
            return LLMResponse(
                content="",
                model=request.model_name or "vllm-model",
                provider=self.provider_name,
                error=f"vLLM inference error: {exc}",
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Stream a chat completion response from vLLM.

        vLLM's streaming requires special handling. This implementation
        generates the full response in the executor and yields it in chunks
        to maintain the streaming interface.

        Args:
            request: Standardized LLM request.

        Yields:
            String chunks of the generated text.
        """
        try:
            self._total_requests += 1
            await self._ensure_initialized()

            # Convert to vLLM format
            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

            # Issue #4524: only apply chat_template when explicitly set
            api_kwargs = request.metadata.get("api_kwargs", {})
            chat_template = request.metadata.get("chat_template")
            inference_kwargs = {
                "temperature": api_kwargs.get("temperature", 0.7),
                "max_tokens": api_kwargs.get("max_tokens", 512),
                "top_p": api_kwargs.get("top_p", 0.95),
                "top_k": api_kwargs.get("top_k", -1),
            }
            if chat_template:
                inference_kwargs["chat_template"] = chat_template

            # Run inference in executor
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                self._vllm_provider.chat_completion,
                messages,
                inference_kwargs,
            )

            # Yield content in chunks to simulate streaming
            content = response["message"]["content"]
            # Simple chunking: yield ~20 characters at a time
            chunk_size = 20
            for i in range(0, len(content), chunk_size):
                yield content[i : i + chunk_size]

        except Exception as exc:
            self._total_errors += 1
            logger.error("vLLM stream completion failed: %s", exc)
            yield f"Error: {exc}"

    async def is_available(self) -> bool:
        """
        Check if vLLM provider is available and healthy.

        Performs a lightweight health check by attempting initialization
        if not already done.

        Returns:
            True if provider is reachable and configured, False otherwise.
        """
        try:
            if not self._initialized:
                await self._ensure_initialized()
            return True
        except Exception as exc:
            logger.warning("vLLM health check failed: %s", exc)
            return False

    async def list_models(self) -> List[str]:
        """
        List available models for vLLM.

        Returns the currently loaded model plus recommended models
        from the vLLM module.

        Returns:
            List of model identifiers.
        """
        try:
            from .vllm_provider import RECOMMENDED_MODELS

            if self._initialized and self._vllm_provider:
                current_model = self._vllm_provider.model_name
                return [current_model] + list(RECOMMENDED_MODELS.keys())
            else:
                return list(RECOMMENDED_MODELS.keys())
        except Exception as exc:
            logger.error("Failed to list vLLM models: %s", exc)
            return []

    def get_stats(self) -> Dict[str, Any]:
        """
        Get provider statistics including model info.

        Returns:
            Dict with request counts, error rates, and model metadata.
        """
        stats = super().get_stats()
        if self._initialized and self._vllm_provider:
            stats.update(
                {
                    "model_name": self._vllm_provider.model_name,
                    "dtype": self._vllm_provider.dtype,
                    "tensor_parallel_size": self._vllm_provider.tensor_parallel_size,
                }
            )
        return stats

    async def cleanup(self) -> None:
        """Clean up vLLM resources."""
        if self._vllm_provider and self._initialized:
            try:
                await self._vllm_provider.cleanup()
                self._initialized = False
                logger.info("vLLM provider cleaned up")
            except Exception as exc:
                logger.error("Error during vLLM cleanup: %s", exc)


__all__ = ["VLLMBaseProvider"]
