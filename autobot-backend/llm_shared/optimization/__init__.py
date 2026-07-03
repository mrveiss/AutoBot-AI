# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LLM Optimization Package - Provider-aware optimization strategies.

This package provides optimization routing for both local (Ollama, vLLM) and
cloud (OpenAI, Anthropic) providers, applying appropriate strategies based
on provider type.

Issue #717: Efficient Inference Design implementation.
"""

# Expose submodules as package attributes so @patch("...optimization.<submodule>.X")
# resolves correctly under pytest --import-mode=importlib (#5728)
from . import (  # noqa: E402,F401  # intentional re-export
    attention_backend,
    flash_attention,
    hf_quantizer,
    meta_eviction,
    model_inspector,
    ssm_kernels,
    token_optimizer,
)
from .attention_backend import AttentionBackend as ModelAttentionBackend
from .attention_backend import (
    AttentionBackendSelector,
)
from .attention_backend import ModelConfig as AttentionModelConfig
from .attention_backend import (
    get_attention_backend_selector,
)
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
from .hf_quantizer import (
    HfQuantizerWrapper,
    LayerLoadResult,
    QuantizationType,
    QuantizedLayerLoader,
    QuantizerConfig,
    detect_quantization,
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
from .kv_cache import (
    RTX_4070_KV_CACHE_FRACTION,
    RTX_4070_VRAM_BYTES,
    KVCacheConfig,
    KVCacheManager,
    LayerKVCache,
)
from .layer_inference import (
    LayerInferenceConfig,
    LayerInferenceEngine,
    LayerInferenceStats,
)
from .meta_eviction import (
    EvictionStats,
    MetaDeviceEvictionManager,
    clean_memory,
    evict_layer_to_meta,
    get_gpu_memory_allocated,
)
from .model_inspector import ModelInfo, clear_cache, inspect_model
from .ssm_kernels import (
    HybridLayerPlan,
    HybridRouter,
    LayerKind,
    LinearAttentionConfig,
    LinearAttentionKernel,
    SSMConfig,
    SSMScanKernel,
    elu_feature_map,
)
from .pipeline import LayerInferencePipeline, PipelineConfig, PreparedPipeline
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
    # End-to-end pipeline (Issue #3140)
    "LayerInferencePipeline",
    "PipelineConfig",
    "PreparedPipeline",
    # Empty-weight Model Inspector (Issue #1945)
    "ModelInfo",
    "inspect_model",
    "clear_cache",
    # SSM / Linear / Hybrid kernels (Issue #10724)
    "SSMScanKernel",
    "SSMConfig",
    "LinearAttentionKernel",
    "LinearAttentionConfig",
    "HybridRouter",
    "HybridLayerPlan",
    "LayerKind",
    "elu_feature_map",
]
