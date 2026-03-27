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
from .flash_attention import (
    AttentionBackend,
    AttentionOutput,
    FlashAttentionConfig,
    FlashAttentionV2,
    GrowingKVCache,
    create_flash_attention,
    detect_backend,
)
from .inference_utils import (
    InferenceConfig,
    InferenceMode,
    LastLogitOptimizer,
    LogitSliceResult,
    MemoryStats,
    slice_hidden_for_generation,
)
from .integration import (
    OptimizationMetrics,
    OptimizedLLMMiddleware,
    get_optimization_middleware,
)
from .profiler import INFERENCE_STAGES, LayeredProfiler
from .prompt_compressor import CompressionConfig, CompressionResult, PromptCompressor
from .rate_limiter import RateLimitConfig, RateLimitError, RateLimitHandler
from .router import (
    OptimizationCategory,
    OptimizationConfig,
    OptimizationRouter,
    get_optimization_router,
)
from .token_optimizer import (
    TokenOptimizer,
    TokenOptimizerConfig,
    TokenSavingsRecord,
    get_token_optimizer,
)

__all__ = [
    # Router
    "OptimizationRouter",
    "OptimizationCategory",
    "OptimizationConfig",
    "get_optimization_router",
    # Flash Attention
    "FlashAttentionV2",
    "FlashAttentionConfig",
    "AttentionBackend",
    "AttentionOutput",
    "GrowingKVCache",
    "create_flash_attention",
    "detect_backend",
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
    # Inference Utilities (Issue #1968)
    "LastLogitOptimizer",
    "InferenceConfig",
    "InferenceMode",
    "LogitSliceResult",
    "MemoryStats",
    "slice_hidden_for_generation",
    # Integration
    "OptimizedLLMMiddleware",
    "OptimizationMetrics",
    "get_optimization_middleware",
    # Token Optimizer
    "TokenOptimizer",
    "TokenOptimizerConfig",
    "TokenSavingsRecord",
    "get_token_optimizer",
    # Profiler (Issue #1956)
    "LayeredProfiler",
    "INFERENCE_STAGES",
]
