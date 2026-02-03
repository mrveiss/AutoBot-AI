# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Provider Health Checking System

Provides unified health checking for all LLM providers (Ollama, OpenAI, Anthropic, Google).
Ensures providers are available before attempting to use them.
"""

from .base import ProviderHealthResult, ProviderStatus
from .manager import ProviderHealthManager
from .providers import (
    AnthropicHealth,
    GoogleHealth,
    OllamaHealth,
    OpenAIHealth,
)

__all__ = [
    "ProviderHealthResult",
    "ProviderStatus",
    "ProviderHealthManager",
    "OllamaHealth",
    "OpenAIHealth",
    "AnthropicHealth",
    "GoogleHealth",
]
