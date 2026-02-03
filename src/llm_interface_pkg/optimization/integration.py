# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Optimization Integration - Connect optimization components to LLMInterface.

Provides middleware that automatically applies appropriate optimizations
based on provider type before/after LLM requests.

Issue #717: Efficient Inference Design implementation.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Dict

from ..models import LLMRequest, LLMResponse
from ..types import ProviderType
from .cloud_batcher import CloudRequestBatcher
from .connection_pool import ConnectionPoolManager, PoolConfig
from .prompt_compressor import CompressionConfig, PromptCompressor
from .rate_limiter import RateLimitConfig, RateLimitHandler
from .router import OptimizationCategory, OptimizationConfig, get_optimization_router

logger = logging.getLogger(__name__)


@dataclass
class OptimizationMetrics:
    """Aggregate metrics from all optimization components."""

    total_requests: int = 0
    requests_with_compression: int = 0
    compression_tokens_saved: int = 0
    cache_hits: int = 0
    batched_requests: int = 0
    rate_limits_handled: int = 0
    avg_latency_improvement_ms: float = 0.0


class OptimizedLLMMiddleware:
    """
    Middleware that wraps LLM requests with appropriate optimizations.

    Automatically applies:
    - Prompt compression (local + cloud)
    - Request batching (cloud only)
    - Connection pooling (cloud only)
    - Rate limit handling (cloud only)
    - Response caching integration

    Typical usage:
        middleware = OptimizedLLMMiddleware()
        response = await middleware.execute(request, llm_handler)
    """

    def __init__(
        self,
        optimization_config: OptimizationConfig = None,
        compression_config: CompressionConfig = None,
        pool_config: PoolConfig = None,
        rate_limit_config: RateLimitConfig = None,
    ):
        """
        Initialize optimization middleware.

        Args:
            optimization_config: Router configuration
            compression_config: Prompt compressor configuration
            pool_config: Connection pool configuration
            rate_limit_config: Rate limit handler configuration
        """
        self._router = get_optimization_router(optimization_config)
        self._compressor = PromptCompressor(compression_config)
        self._pool_manager = ConnectionPoolManager(pool_config)
        self._rate_limiter = RateLimitHandler(rate_limit_config)

        # Per-provider batchers (created on demand)
        self._batchers: Dict[str, CloudRequestBatcher] = {}

        # Metrics
        self._metrics = OptimizationMetrics()
        self._lock = asyncio.Lock()

        logger.info("OptimizedLLMMiddleware initialized")

    def _get_provider_type(self, request: LLMRequest) -> ProviderType:
        """Convert request provider to ProviderType enum."""
        if request.provider:
            if isinstance(request.provider, ProviderType):
                return request.provider
            try:
                return ProviderType(request.provider)
            except ValueError:
                pass

        # Infer from model name
        model = request.model_name or ""
        if "gpt" in model.lower() or "openai" in model.lower():
            return ProviderType.OPENAI
        elif "claude" in model.lower():
            return ProviderType.ANTHROPIC
        elif "llama" in model.lower() or "mistral" in model.lower():
            return ProviderType.OLLAMA

        return ProviderType.OLLAMA  # Default to local

    async def execute(
        self,
        request: LLMRequest,
        handler: Callable[[LLMRequest], Coroutine[Any, Any, LLMResponse]],
    ) -> LLMResponse:
        """
        Execute request with optimizations applied.

        Args:
            request: The LLM request
            handler: The actual LLM handler function

        Returns:
            LLMResponse with optimizations applied
        """
        start_time = time.time()
        provider_type = self._get_provider_type(request)

        async with self._lock:
            self._metrics.total_requests += 1

        # Pre-request optimizations
        optimized_request = await self._apply_pre_optimizations(request, provider_type)

        # Execute with appropriate strategy
        if self._router.is_cloud_provider(provider_type):
            response = await self._execute_cloud_optimized(
                optimized_request, handler, provider_type
            )
        else:
            response = await self._execute_local_optimized(
                optimized_request, handler, provider_type
            )

        # Post-request optimizations
        response = await self._apply_post_optimizations(response, provider_type)

        # Update latency metrics
        latency_ms = (time.time() - start_time) * 1000
        await self._update_latency_metrics(latency_ms)

        return response

    async def _apply_pre_optimizations(
        self, request: LLMRequest, provider_type: ProviderType
    ) -> LLMRequest:
        """Apply pre-request optimizations."""
        # Apply prompt compression if enabled
        if self._router.should_apply(
            OptimizationCategory.PROMPT_COMPRESSION, provider_type
        ):
            request = await self._compress_request_prompts(request)

        return request

    async def _compress_request_prompts(self, request: LLMRequest) -> LLMRequest:
        """Compress prompts in request messages."""
        if not request.messages:
            return request

        original_tokens = 0
        compressed_tokens = 0

        compressed_messages = []
        for msg in request.messages:
            content = msg.get("content", "")
            if not content:
                compressed_messages.append(msg)
                continue

            result = self._compressor.compress(content)
            original_tokens += result.original_tokens
            compressed_tokens += result.compressed_tokens

            compressed_messages.append(
                {
                    **msg,
                    "content": result.compressed_text,
                }
            )

        # Update metrics
        tokens_saved = original_tokens - compressed_tokens
        if tokens_saved > 0:
            async with self._lock:
                self._metrics.requests_with_compression += 1
                self._metrics.compression_tokens_saved += tokens_saved

        # Create new request with compressed messages
        return LLMRequest(
            messages=compressed_messages,
            llm_type=request.llm_type,
            provider=request.provider,
            model_name=request.model_name,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            top_p=request.top_p,
            frequency_penalty=request.frequency_penalty,
            presence_penalty=request.presence_penalty,
            stop=request.stop,
            stream=request.stream,
            structured_output=request.structured_output,
            timeout=request.timeout,
            retry_count=request.retry_count,
            fallback_enabled=request.fallback_enabled,
            metadata={
                **request.metadata,
                "original_tokens": original_tokens,
                "compressed_tokens": compressed_tokens,
            },
            request_id=request.request_id,
        )

    async def _execute_cloud_optimized(
        self,
        request: LLMRequest,
        handler: Callable[[LLMRequest], Coroutine[Any, Any, LLMResponse]],
        provider_type: ProviderType,
    ) -> LLMResponse:
        """Execute cloud request with cloud-specific optimizations."""
        provider_name = provider_type.value

        # Apply rate limit handling
        if self._router.should_apply(
            OptimizationCategory.RATE_LIMIT_HANDLING, provider_type
        ):
            try:
                response = await self._rate_limiter.execute_with_retry(
                    lambda: handler(request),
                    provider=provider_name,
                )
                return response
            except Exception:
                async with self._lock:
                    self._metrics.rate_limits_handled += 1
                raise

        return await handler(request)

    async def _execute_local_optimized(
        self,
        request: LLMRequest,
        handler: Callable[[LLMRequest], Coroutine[Any, Any, LLMResponse]],
        provider_type: ProviderType,
    ) -> LLMResponse:
        """Execute local request (GPU optimizations handled by provider)."""
        # Local optimizations (speculative, FlashInfer, etc.) are handled
        # directly by vLLM/Ollama providers. This middleware just ensures
        # prompt compression is applied.
        return await handler(request)

    async def _apply_post_optimizations(
        self, response: LLMResponse, provider_type: ProviderType
    ) -> LLMResponse:
        """Apply post-response optimizations."""
        # Currently no post-response optimizations needed
        # Future: Response validation, token counting, etc.
        return response

    async def _update_latency_metrics(self, latency_ms: float) -> None:
        """Update rolling average latency improvement."""
        async with self._lock:
            total = self._metrics.total_requests
            current_avg = self._metrics.avg_latency_improvement_ms
            # Rolling average
            self._metrics.avg_latency_improvement_ms = (
                current_avg * (total - 1) + latency_ms
            ) / total

    def get_metrics(self) -> Dict[str, Any]:
        """Get optimization metrics."""
        router_summary = self._router.get_optimization_summary(ProviderType.OLLAMA)

        return {
            "total_requests": self._metrics.total_requests,
            "requests_with_compression": self._metrics.requests_with_compression,
            "compression_tokens_saved": self._metrics.compression_tokens_saved,
            "cache_hits": self._metrics.cache_hits,
            "batched_requests": self._metrics.batched_requests,
            "rate_limits_handled": self._metrics.rate_limits_handled,
            "avg_latency_ms": round(self._metrics.avg_latency_improvement_ms, 2),
            "rate_limiter": self._rate_limiter.get_metrics(),
            "connection_pools": self._pool_manager.get_metrics(),
            "optimization_config": router_summary,
        }

    async def cleanup(self) -> None:
        """Cleanup resources."""
        # Close connection pools
        await self._pool_manager.close_all()

        # Shutdown batchers
        for batcher in self._batchers.values():
            await batcher.shutdown()
        self._batchers.clear()

        logger.info("OptimizedLLMMiddleware cleaned up")


# Global middleware instance
_middleware: OptimizedLLMMiddleware = None
_middleware_lock = asyncio.Lock()


async def get_optimization_middleware(
    optimization_config: OptimizationConfig = None,
) -> OptimizedLLMMiddleware:
    """
    Get or create the global optimization middleware.

    Args:
        optimization_config: Configuration (only used on first call)

    Returns:
        OptimizedLLMMiddleware singleton instance
    """
    global _middleware
    if _middleware is None:
        async with _middleware_lock:
            if _middleware is None:
                _middleware = OptimizedLLMMiddleware(optimization_config)
    return _middleware


__all__ = [
    "OptimizedLLMMiddleware",
    "OptimizationMetrics",
    "get_optimization_middleware",
]
