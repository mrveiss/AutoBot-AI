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
from .kv_cache import (
    KVCacheConfig,
    KVCacheManager,
    LayerKVCache,
    RTX_4070_KV_CACHE_FRACTION,
    RTX_4070_VRAM_BYTES,
)
from .hf_quantizer import (
    HfQuantizerWrapper,
    LayerLoadResult,
    QuantizerConfig,
    QuantizationType,
    QuantizedLayerLoader,
    detect_quantization,
)
from .meta_eviction import (
    EvictionStats,
    MetaDeviceEvictionManager,
    clean_memory,
    evict_layer_to_meta,
    get_gpu_memory_allocated,
)
from .token_optimizer import (
    TokenOptimizer,
    TokenOptimizerConfig,
    TokenSavingsRecord,
    get_token_optimizer,
)
from .attention_backend import (
    AttentionBackend as ModelAttentionBackend,
    AttentionBackendSelector,
    ModelConfig as AttentionModelConfig,
    get_attention_backend_selector,
)
from .layer_inference import (
    LayerInferenceConfig,
    LayerInferenceEngine,
    LayerInferenceStats,
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
    # HF Quantizer (Issue #1954)
    "QuantizationType",
    "detect_quantization",
    "HfQuantizerWrapper",
    "QuantizerConfig",
    "QuantizedLayerLoader",
    "LayerLoadResult",
    # KV Cache Manager (Issue #1964)
    "KVCacheConfig",
    "KVCacheManager",
    "LayerKVCache",
    "RTX_4070_KV_CACHE_FRACTION",
    "RTX_4070_VRAM_BYTES",
<<<<<<< HEAD
    # Attention Backend Selector (Issue #1951)
    "ModelAttentionBackend",
    "AttentionBackendSelector",
    "AttentionModelConfig",
    "get_attention_backend_selector",
    # Meta Device Eviction (Issue #1952)
    "clean_memory",
    "evict_layer_to_meta",
    "get_gpu_memory_allocated",
    "EvictionStats",
    "MetaDeviceEvictionManager",
    # Layer-by-layer Inference (Issue #1946)
    "LayerInferenceConfig",
    "LayerInferenceEngine",
    "LayerInferenceStats",
]
