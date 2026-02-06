# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Interface Facade - Backward compatibility layer.

This module provides backward compatibility for existing imports while
delegating to the refactored llm_interface_pkg package.

Refactored as part of Issue #381 god class refactoring.
Original: 1,449 lines → Facade: ~80 lines (94% reduction)

For new code, import directly from llm_interface_pkg:
    from llm_interface_pkg import LLMInterface, LLMSettings, ProviderType
"""

# Re-export everything from the refactored package
from llm_interface_pkg import (
    # Types
    ProviderType,
    LLMType,
    # Models
    LLMSettings,
    LLMResponse,
    ChatMessage,
    LLMRequest,
    # Hardware
    HardwareDetector,
    TORCH_AVAILABLE,
    # Streaming
    StreamingManager,
    # Mock providers
    LocalLLM,
    MockPalm,
    local_llm,
    palm,
    # Main interface
    LLMInterface,
    # Providers
    OllamaProvider,
    OpenAIProvider,
    TransformersProvider,
    VLLMProviderHandler,
    MockHandler,
    LocalHandler,
)

# Import additional dependencies that may be expected by consumers
from config import UnifiedConfigManager

# Create singleton config instance for backward compatibility
config = UnifiedConfigManager()

# Optional imports for backward compatibility
try:
    from prompt_manager import prompt_manager
except ImportError:
    prompt_manager = None

try:
    from autobot_shared.logging_manager import get_llm_logger

    logger = get_llm_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# LLM Pattern Analyzer integration (Issue #229)
try:
    from backend.api.analytics_llm_patterns import (
        get_pattern_analyzer,
        UsageRecordRequest,
    )

    PATTERN_ANALYZER_AVAILABLE = True
except ImportError:
    PATTERN_ANALYZER_AVAILABLE = False
    UsageRecordRequest = None
    get_pattern_analyzer = None

# OpenAI availability flag
try:
    import openai

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None

# Re-export get_llm_interface from resource_factory for backward compatibility
from utils.resource_factory import ResourceFactory

get_llm_interface = ResourceFactory.get_llm_interface

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
    # Backward compatibility
    "config",
    "prompt_manager",
    "logger",
    "PATTERN_ANALYZER_AVAILABLE",
    "UsageRecordRequest",
    "get_pattern_analyzer",
    "OPENAI_AVAILABLE",
    "openai",
    "get_llm_interface",
]
