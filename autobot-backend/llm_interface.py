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
from llm_interface_pkg import (  # Types; Models; Hardware; Streaming; Mock providers; Main interface; Providers
    TORCH_AVAILABLE,
    ChatMessage,
    HardwareDetector,
    LLMInterface,
    LLMRequest,
    LLMResponse,
    LLMSettings,
    LLMType,
    LocalHandler,
    LocalLLM,
    MockHandler,
    MockPalm,
    OllamaProvider,
    OpenAIProvider,
    ProviderType,
    StreamingManager,
    TransformersProvider,
    VLLMProviderHandler,
    local_llm,
    palm,
)

# Import additional dependencies that may be expected by consumers
from config import ConfigManager

# Create singleton config instance for backward compatibility
config = ConfigManager()

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
    from api.analytics_llm_patterns import UsageRecordRequest, get_pattern_analyzer

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


# Lazy re-export to avoid circular dependency (#1210)
# resource_factory imports back into this module's consumers
def __getattr__(name):
    if name == "get_llm_interface":
        from utils.resource_factory import ResourceFactory

        return ResourceFactory.get_llm_interface
    raise AttributeError(f"module 'llm_interface' has no attribute {name}")


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
]
