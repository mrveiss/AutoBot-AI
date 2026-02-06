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

from .router import (
    OptimizationRouter,
    OptimizationCategory,
    OptimizationConfig,
    get_optimization_router,
)
from .cloud_batcher import CloudRequestBatcher, BatchResult
from .connection_pool import ConnectionPoolManager, PoolConfig
from .rate_limiter import RateLimitHandler, RateLimitConfig, RateLimitError
from .prompt_compressor import PromptCompressor, CompressionResult, CompressionConfig
from .integration import (
    OptimizedLLMMiddleware,
    OptimizationMetrics,
    get_optimization_middleware,
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
