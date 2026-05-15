# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Legacy provider implementations retained as shared infra (#3185).

After LLMInterface retirement (#3185), only ``ollama`` (back-edge for the
canonical ``llm_providers.OllamaProvider`` delegate), ``transformers_provider``,
and ``mock_handler`` remain. The duplicate Anthropic/OpenAI/Groq/vLLM
implementations were removed; canonical versions live in ``llm_providers/``.
"""

from .mock_handler import LocalHandler, MockHandler
from .ollama import OllamaProvider
from .transformers_provider import TransformersProvider

__all__ = [
    "OllamaProvider",
    "TransformersProvider",
    "MockHandler",
    "LocalHandler",
]
