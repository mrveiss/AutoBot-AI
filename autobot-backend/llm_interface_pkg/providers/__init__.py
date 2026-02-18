# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Providers Package - Provider-specific implementations for different LLM backends.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

from .mock_handler import LocalHandler, MockHandler
from .ollama import OllamaProvider
from .openai_provider import OpenAIProvider
from .transformers_provider import TransformersProvider
from .vllm_provider import VLLMProviderHandler

__all__ = [
    "OllamaProvider",
    "OpenAIProvider",
    "TransformersProvider",
    "VLLMProviderHandler",
    "MockHandler",
    "LocalHandler",
]
