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

# Issue #551: L1/L2 dual-tier caching
from .cache import CachedResponse, LLMResponseCache, get_llm_cache

# Hardware detection
from .hardware import TORCH_AVAILABLE, HardwareDetector

# Mock providers
from .mock_providers import LocalLLM, MockPalm, local_llm, palm

# Models
from .models import ChatMessage, LLMRequest, LLMResponse, LLMSettings

# Provider implementations (legacy — kept as shared infra for ollama back-edge)
from .providers import (
    LocalHandler,
    MockHandler,
    OllamaProvider,
    TransformersProvider,
)

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
]
