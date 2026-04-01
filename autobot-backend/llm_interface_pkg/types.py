# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Interface Types - Enums and constants for LLM operations.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

from enum import Enum


class ProviderType(Enum):
    """Supported LLM providers."""

    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    VLLM = "vllm"
    HUGGINGFACE = "huggingface"
    TRANSFORMERS = "transformers"
    MOCK = "mock"
    LOCAL = "local"
    AI_STACK = "ai_stack"  # Issue #1403
    PROCESS = "process"  # Issue #1403
    LAYER_INFERENCE = "layer_inference"  # Issue #3104


class LLMType(Enum):
    """Types of LLM usage contexts."""

    ORCHESTRATOR = "orchestrator"
    TASK = "task"
    CHAT = "chat"
    RAG = "rag"
    ANALYSIS = "analysis"
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    GENERAL = "general"


__all__ = [
    "ProviderType",
    "LLMType",
]
