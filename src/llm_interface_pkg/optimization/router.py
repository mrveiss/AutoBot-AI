# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Optimization Router - Provider-aware optimization strategy routing.

Routes optimization strategies based on provider type. Local providers get
GPU-level optimizations while cloud providers get API-level optimizations.

Issue #717: Efficient Inference Design implementation.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Set

from ..types import ProviderType

logger = logging.getLogger(__name__)


class OptimizationCategory(Enum):
    """Categories of optimization strategies."""

    # GPU/Local-only optimizations
    SPECULATIVE_DECODING = "speculative_decoding"
    FLASH_ATTENTION = "flash_attention"
    CUDA_GRAPHS = "cuda_graphs"
    MEDUSA_HEADS = "medusa_heads"
    QUANTIZATION = "quantization"
    KV_CACHE_OPTIMIZATION = "kv_cache_optimization"
    CONTINUOUS_BATCHING = "continuous_batching"
    PREFIX_CACHING = "prefix_caching"

    # Cloud/API-level optimizations
    CONNECTION_POOLING = "connection_pooling"
    API_REQUEST_BATCHING = "api_request_batching"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    RATE_LIMIT_HANDLING = "rate_limit_handling"

    # Universal optimizations (both local and cloud)
    RESPONSE_CACHING = "response_caching"
    PROMPT_COMPRESSION = "prompt_compression"
    REQUEST_DEDUPLICATION = "request_deduplication"


@dataclass
class OptimizationConfig:
    """Configuration for optimization strategies."""

    # Speculation settings
    speculation_enabled: bool = False
    speculation_draft_model: str = ""
    speculation_num_tokens: int = 5
    speculation_use_ngram: bool = False

    # Quantization settings
    quantization_enabled: bool = False
    quantization_type: str = "none"  # none, int8, int4, gptq, awq

    # Cloud settings
    connection_pool_size: int = 100
    batch_window_ms: int = 50
    max_batch_size: int = 10
    retry_max_attempts: int = 3

    # Prompt compression
    prompt_compression_enabled: bool = True
    prompt_compression_ratio: float = 0.7

    # Response caching
    cache_enabled: bool = True
    cache_l1_size: int = 100
    cache_l2_ttl: int = 300


class OptimizationRouter:
    """
    Route optimization strategies based on provider type.

    Local providers (Ollama, vLLM) get GPU-level optimizations like speculative
    decoding, FlashInfer, and quantization. Cloud providers (OpenAI, Anthropic)
    get API-level optimizations like connection pooling and request batching.
    """

    # Optimizations that only apply to local/GPU-based inference
    LOCAL_ONLY_OPTIMIZATIONS: Set[OptimizationCategory] = {
        OptimizationCategory.SPECULATIVE_DECODING,
        OptimizationCategory.FLASH_ATTENTION,
        OptimizationCategory.CUDA_GRAPHS,
        OptimizationCategory.MEDUSA_HEADS,
        OptimizationCategory.QUANTIZATION,
        OptimizationCategory.KV_CACHE_OPTIMIZATION,
        OptimizationCategory.CONTINUOUS_BATCHING,
        OptimizationCategory.PREFIX_CACHING,
    }

    # Optimizations that only apply to cloud API providers
    CLOUD_ONLY_OPTIMIZATIONS: Set[OptimizationCategory] = {
        OptimizationCategory.CONNECTION_POOLING,
        OptimizationCategory.API_REQUEST_BATCHING,
        OptimizationCategory.RETRY_WITH_BACKOFF,
        OptimizationCategory.RATE_LIMIT_HANDLING,
    }

    # Optimizations that apply to all providers
    UNIVERSAL_OPTIMIZATIONS: Set[OptimizationCategory] = {
        OptimizationCategory.RESPONSE_CACHING,
        OptimizationCategory.PROMPT_COMPRESSION,
        OptimizationCategory.REQUEST_DEDUPLICATION,
    }

    # Provider classification
    LOCAL_PROVIDERS: Set[ProviderType] = {
        ProviderType.OLLAMA,
        ProviderType.VLLM,
        ProviderType.TRANSFORMERS,
        ProviderType.HUGGINGFACE,
        ProviderType.LOCAL,
    }

    CLOUD_PROVIDERS: Set[ProviderType] = {
        ProviderType.OPENAI,
        ProviderType.ANTHROPIC,
    }

    def __init__(self, config: OptimizationConfig = None):
        """
        Initialize optimization router.

        Args:
            config: Optimization configuration (uses defaults if None)
        """
        self.config = config or OptimizationConfig()
        self._enabled_optimizations: Dict[ProviderType, Set[OptimizationCategory]] = {}
        self._initialize_provider_optimizations()

    def _initialize_provider_optimizations(self) -> None:
        """Initialize optimization sets for each provider type."""
        for provider in ProviderType:
            self._enabled_optimizations[provider] = self._get_applicable_optimizations(
                provider
            )

    def _get_applicable_optimizations(
        self, provider: ProviderType
    ) -> Set[OptimizationCategory]:
        """
        Get applicable optimizations for a provider type.

        Args:
            provider: The LLM provider type

        Returns:
            Set of applicable optimization categories
        """
        optimizations = set(self.UNIVERSAL_OPTIMIZATIONS)

        if provider in self.LOCAL_PROVIDERS:
            optimizations.update(self.LOCAL_ONLY_OPTIMIZATIONS)
        elif provider in self.CLOUD_PROVIDERS:
            optimizations.update(self.CLOUD_ONLY_OPTIMIZATIONS)

        return optimizations

    def is_local_provider(self, provider: ProviderType) -> bool:
        """Check if provider is a local/GPU-based provider."""
        return provider in self.LOCAL_PROVIDERS

    def is_cloud_provider(self, provider: ProviderType) -> bool:
        """Check if provider is a cloud API provider."""
        return provider in self.CLOUD_PROVIDERS

    def should_apply(
        self, optimization: OptimizationCategory, provider: ProviderType
    ) -> bool:
        """
        Check if an optimization should be applied for a provider.

        Args:
            optimization: The optimization category to check
            provider: The LLM provider type

        Returns:
            True if the optimization applies to this provider
        """
        applicable = optimization in self._enabled_optimizations.get(provider, set())

        # Check config-based enablement
        if applicable:
            applicable = self._is_optimization_enabled(optimization)

        return applicable

    def _is_optimization_enabled(self, optimization: OptimizationCategory) -> bool:
        """Check if optimization is enabled in config."""
        config_mapping = {
            OptimizationCategory.SPECULATIVE_DECODING: self.config.speculation_enabled,
            OptimizationCategory.QUANTIZATION: self.config.quantization_enabled,
            OptimizationCategory.PROMPT_COMPRESSION: self.config.prompt_compression_enabled,
            OptimizationCategory.RESPONSE_CACHING: self.config.cache_enabled,
        }
        # Default to True for optimizations not in mapping
        return config_mapping.get(optimization, True)

    def get_optimizations(self, provider: ProviderType) -> Set[OptimizationCategory]:
        """
        Get all applicable optimizations for a provider.

        Args:
            provider: The LLM provider type

        Returns:
            Set of applicable optimization categories
        """
        return self._enabled_optimizations.get(provider, set())

    def get_enabled_optimizations(
        self, provider: ProviderType
    ) -> Set[OptimizationCategory]:
        """
        Get all enabled optimizations for a provider (respects config).

        Args:
            provider: The LLM provider type

        Returns:
            Set of enabled optimization categories
        """
        applicable = self.get_optimizations(provider)
        return {opt for opt in applicable if self._is_optimization_enabled(opt)}

    def get_optimization_summary(self, provider: ProviderType) -> Dict[str, bool]:
        """
        Get summary of all optimizations and their status for a provider.

        Args:
            provider: The LLM provider type

        Returns:
            Dict mapping optimization name to enabled status
        """
        summary = {}
        for opt in OptimizationCategory:
            applicable = opt in self._enabled_optimizations.get(provider, set())
            enabled = applicable and self._is_optimization_enabled(opt)
            summary[opt.value] = enabled
        return summary

    def log_optimization_status(self, provider: ProviderType) -> None:
        """Log optimization status for debugging."""
        summary = self.get_optimization_summary(provider)
        enabled = [k for k, v in summary.items() if v]
        disabled = [k for k, v in summary.items() if not v]

        logger.info(
            "Optimization status for %s - Enabled: %s, Disabled: %s",
            provider.value,
            enabled,
            disabled,
        )


# Global router instance (lazy initialization)
_optimization_router: OptimizationRouter = None


def get_optimization_router(config: OptimizationConfig = None) -> OptimizationRouter:
    """
    Get or create the global optimization router instance.

    Args:
        config: Optional configuration (only used on first call)

    Returns:
        OptimizationRouter singleton instance
    """
    global _optimization_router
    if _optimization_router is None:
        _optimization_router = OptimizationRouter(config)
    return _optimization_router


__all__ = [
    "OptimizationCategory",
    "OptimizationConfig",
    "OptimizationRouter",
    "get_optimization_router",
]
