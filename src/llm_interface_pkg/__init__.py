# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Interface Package - Consolidated interface for all LLM providers.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
This package provides a modular, maintainable structure for LLM operations.

Issue #551: Added L1/L2 caching, provider fallback, and streaming protection.

Package Structure:
    types.py       - Enums (ProviderType, LLMType)
    models.py      - Dataclasses (LLMSettings, LLMResponse, ChatMessage, LLMRequest)
    hardware.py    - Hardware detection and backend selection
    streaming.py   - Streaming state and failure management
    cache.py       - L1/L2 dual-tier caching (Issue #551)
    mock_providers.py - Local fallback and mock implementations
    interface.py   - Main LLMInterface class
    providers/     - Provider-specific implementations (Ollama, OpenAI, vLLM, etc.)
"""

# Types
from .types import (
    ProviderType,
    LLMType,
)

# Models
from .models import (
    LLMSettings,
    LLMResponse,
    ChatMessage,
    LLMRequest,
)

# Hardware detection
from .hardware import (
    HardwareDetector,
    TORCH_AVAILABLE,
)

# Streaming management
from .streaming import (
    StreamingManager,
)

# Issue #551: L1/L2 dual-tier caching
from .cache import (
    LLMResponseCache,
    CachedResponse,
    get_llm_cache,
    get_llm_cache_async,
)

# Mock providers
from .mock_providers import (
    LocalLLM,
    MockPalm,
    local_llm,
    palm,
)

# Main interface
from .interface import (
    LLMInterface,
)

# Provider implementations
from .providers import (
    OllamaProvider,
    OpenAIProvider,
    TransformersProvider,
    VLLMProviderHandler,
    MockHandler,
    LocalHandler,
)

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
    "get_llm_cache_async",
    # Mock providers
    "LocalLLM",
    "MockPalm",
    "local_llm",
    "palm",
    # Main interface
    "LLMInterface",
    # Providers
    "OllamaProvider",
    "OpenAIProvider",
    "TransformersProvider",
    "VLLMProviderHandler",
    "MockHandler",
    "LocalHandler",
]
