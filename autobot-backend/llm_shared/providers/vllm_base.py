# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
vLLM Base Provider - Wraps VLLMProvider in BaseProvider interface for registry integration.

Issue #4341: Model Provider Flexibility & Vendor-Agnostic Switching

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List

from autobot_shared.logging_manager import get_logger
from llm_shared.models import LLMRequest, LLMResponse
from llm_shared.types import ProviderType

from ..base_provider import BaseProvider
from .vllm import VLLMProvider

logger = get_logger(__name__)


class VLLMBaseProvider(BaseProvider):
    """
    Standardized BaseProvider wrapper for vLLM.

    Wraps VLLMProvider and adapts it to the BaseProvider interface for
    integration with the provider registry, fallback chains, and health monitoring.
    """

    provider_name = ProviderType.VLLM.value

    def __init__(self, settings: Dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        if not self.settings or "model" not in self.settings:
            raise ValueError('VLLMBaseProvider requires "model" in settings')

        self._vllm_provider: VLLMProvider | None = None
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
        """Execute a chat completion request via vLLM."""
        try:
            self._total_requests += 1
            await self._ensure_initialized()

            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

            # Issue #4524: only apply chat_template when explicitly set
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

            response = await asyncio.get_running_loop().run_in_executor(
                None,
                self._vllm_provider.chat_completion,
                messages,
                inference_kwargs,
            )

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
        """Stream a chat completion response from vLLM."""
        try:
            self._total_requests += 1
            await self._ensure_initialized()

            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

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

            response = await asyncio.get_running_loop().run_in_executor(
                None,
                self._vllm_provider.chat_completion,
                messages,
                inference_kwargs,
            )

            content = response["message"]["content"]
            chunk_size = 20
            for i in range(0, len(content), chunk_size):
                yield content[i : i + chunk_size]

        except Exception as exc:
            self._total_errors += 1
            logger.error("vLLM stream completion failed: %s", exc)
            yield f"Error: {exc}"

    async def is_available(self) -> bool:
        """Check if vLLM provider is available and healthy."""
        try:
            if not self._initialized:
                await self._ensure_initialized()
            return True
        except Exception as exc:
            logger.warning("vLLM health check failed: %s", exc)
            return False

    async def list_models(self) -> List[str]:
        """List available models for vLLM."""
        try:
            from .vllm import RECOMMENDED_MODELS

            if self._initialized and self._vllm_provider:
                current_model = self._vllm_provider.model_name
                return [current_model] + list(RECOMMENDED_MODELS.keys())
            else:
                return list(RECOMMENDED_MODELS.keys())
        except Exception as exc:
            logger.error("Failed to list vLLM models: %s", exc)
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics including model info."""
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
