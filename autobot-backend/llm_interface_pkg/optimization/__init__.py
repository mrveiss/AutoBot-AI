# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Optimization Package - Provider-aware optimization strategies.

This package provides optimization routing for both local (Ollama, vLLM) and
cloud (OpenAI, Anthropic) providers, applying appropriate strategies based
on provider type.

Issue #717: Efficient Inference Design implementation.
"""

from .cloud_batcher import BatchResult, CloudRequestBatcher
from .connection_pool import ConnectionPoolManager, PoolConfig
from .integration import (
    OptimizationMetrics,
    OptimizedLLMMiddleware,
    get_optimization_middleware,
)
from .prompt_compressor import CompressionConfig, CompressionResult, PromptCompressor
from .rate_limiter import RateLimitConfig, RateLimitError, RateLimitHandler
from .router import (
    OptimizationCategory,
    OptimizationConfig,
    OptimizationRouter,
    get_optimization_router,
)

__all__ = [
    # Router
    "OptimizationRouter",
    "OptimizationCategory",
    "OptimizationConfig",
    "get_optimization_router",
    # Cloud Batcher
    "CloudRequestBatcher",
    "BatchResult",
    # Connection Pool
    "ConnectionPoolManager",
    "PoolConfig",
    # Rate Limiter
    "RateLimitHandler",
    "RateLimitConfig",
    "RateLimitError",
    # Prompt Compressor
    "PromptCompressor",
    "CompressionResult",
    "CompressionConfig",
    # Integration
    "OptimizedLLMMiddleware",
    "OptimizationMetrics",
    "get_optimization_middleware",
]
