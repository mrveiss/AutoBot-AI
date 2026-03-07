# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Adapter Package - Pluggable adapter registry for LLM backends (#1403).

Provides a standard interface for all LLM backends with registration,
lookup, fallback behavior, and per-agent configuration.
"""

from .ai_stack_adapter import AIStackAdapter
from .anthropic_adapter import AnthropicAdapter
from .base import (
    AdapterBase,
    AdapterConfig,
    DiagnosticLevel,
    DiagnosticMessage,
    EnvironmentTestResult,
    SessionCodec,
)
from .ollama_adapter import OllamaAdapter
from .openai_adapter import OpenAIAdapter
from .process_adapter import ProcessAdapter
from .registry import AdapterRegistry, get_adapter_registry

__all__ = [
    # Base
    "AdapterBase",
    "AdapterConfig",
    "DiagnosticLevel",
    "DiagnosticMessage",
    "EnvironmentTestResult",
    "SessionCodec",
    # Registry
    "AdapterRegistry",
    "get_adapter_registry",
    # Adapters
    "OllamaAdapter",
    "AIStackAdapter",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "ProcessAdapter",
]
