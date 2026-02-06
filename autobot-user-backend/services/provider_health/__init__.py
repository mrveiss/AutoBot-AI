# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Provider Health Checking System

Provides unified health checking for all LLM providers.
Ensures providers are available before attempting to use them.

Supported Providers (Issue #746):
- Ollama (local)
- OpenAI (cloud)
- Anthropic (cloud)
- Google Gemini (cloud)
- LM Studio (local)
- vLLM (local/server)
"""

from .base import ProviderHealthResult, ProviderStatus
from .manager import ProviderHealthManager
from .providers import (
    AnthropicHealth,
    GoogleHealth,
    LMStudioHealth,
    OllamaHealth,
    OpenAIHealth,
    VLLMHealth,
)

__all__ = [
    "ProviderHealthResult",
    "ProviderStatus",
    "ProviderHealthManager",
    "OllamaHealth",
    "OpenAIHealth",
    "AnthropicHealth",
    "GoogleHealth",
    "LMStudioHealth",
    "VLLMHealth",
]
