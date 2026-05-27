# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM shared-infra package.

After LLMInterface retirement (#3185), this package no longer ships a
god-class orchestrator. Canonical inference lives in
``services.llm_service.LLMService`` over ``llm_providers/``.

What remains here is shared infra reused across the new stack:

    types.py          - Enums (ProviderType, LLMType)
    models.py         - Dataclasses (LLMSettings, LLMResponse, ChatMessage, LLMRequest)
    hardware.py       - Hardware detection and backend selection
    streaming.py      - Streaming state and failure management
    cache.py          - L1/L2 dual-tier caching (Issue #551)
    optimization/     - Prompt compression, rate limiting, connection pooling
    tiered_routing/   - Lightweight vs. complex model routing (Issue #748)
    adapters/         - Adapter registry (Issue #1403) for diagnostic endpoints
    mock_providers.py - Local fallback and mock implementations
    providers/        - Legacy provider impls retained as shared infra (ollama
                        back-edge, transformers, mock_handler)
"""

# Adapter registry (Issue #1403)
from .adapters import AdapterBase, AdapterRegistry, get_adapter_registry

# Pluggable LLM observability (GH#6593)
from .observability import LLMObserver, register
from .observability.otel_observer import OTELObserver
from .observability.prometheus_observer import PrometheusObserver

register(OTELObserver())
register(PrometheusObserver())

# Provider registry and base (canonical imports for MVA-62 consolidation)
# These were in llm_providers/ but are now consolidated in llm_shared
from .base_provider import BaseProvider

# Issue #551: L1/L2 dual-tier caching
from .cache import CachedResponse, LLMResponseCache, get_llm_cache

# Hardware detection
from .hardware import TORCH_AVAILABLE, HardwareDetector

# Mock providers
from .mock_providers import LocalLLM, MockPalm, local_llm, palm
from .model_param_registry import (
    ArchitectureFamily,
    apply_model_defaults,
    apply_prompt_prefix,
    get_architecture_family,
    get_model_kwargs,
    get_prompt_prefix,
    get_provider_model_id,
    resolve_model_name,
)

# Models
from .models import ChatMessage, LLMRequest, LLMResponse, LLMSettings
from .ollama_helpers import call_ollama_generate
from .provider_registry import ProviderRegistry, get_provider_registry

# Provider implementations (legacy — kept as shared infra for ollama back-edge)
from .providers import (
    LocalHandler,
    MockHandler,
    OllamaProvider,
    TransformersProvider,
)

# Issue #8168: Semantic similarity tier-3 cache
from .semantic_cache import SemanticLLMCache

# Streaming management
from .streaming import StreamingManager

# Types
from .types import LLMType, ProviderType

__all__ = [
    # Types
    "ProviderType",
    "LLMType",
    # Models
    "LLMSettings",
    "LLMResponse",
    "ChatMessage",
    "LLMRequest",
    # Hardware
    "HardwareDetector",
    "TORCH_AVAILABLE",
    # Streaming
    "StreamingManager",
    # Cache (Issue #551)
    "LLMResponseCache",
    "CachedResponse",
    "get_llm_cache",
    # Semantic cache (Issue #8168)
    "SemanticLLMCache",
    # Mock providers
    "LocalLLM",
    "MockPalm",
    "local_llm",
    "palm",
    # Providers (legacy shared infra)
    "OllamaProvider",
    "TransformersProvider",
    "MockHandler",
    "LocalHandler",
    # Adapter registry (Issue #1403)
    "AdapterBase",
    "AdapterRegistry",
    "get_adapter_registry",
    # Provider registry and base (MVA-62 consolidation)
    "BaseProvider",
    "ProviderRegistry",
    "get_provider_registry",
    # Model parameter registry (MVA-178)
    "resolve_model_name",
    "get_model_kwargs",
    "get_provider_model_id",
    "apply_model_defaults",
    "get_prompt_prefix",
    "apply_prompt_prefix",
    # Ollama helpers (MVA-178)
    "call_ollama_generate",
    # Observability (GH#6593)
    "LLMObserver",
    "register",
]
