# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LLM Interface Types - Enums and constants for LLM operations.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

from enum import Enum


class ArchitectureFamily(str, Enum):
    """Model architecture family — governs attention backend and context window policy.

    Issue #7347: positive family signal replacing substring-match heuristics.
    """

    TRANSFORMER = "transformer"
    STATE_SPACE = "state_space"  # Mamba / S4 family
    LINEAR_ATTENTION = "linear_attention"
    HYBRID = "hybrid"  # Jamba-style mixed architectures


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
    GROQ = "groq"  # Issue #4096
    MISTRAL = "mistral"  # Issue #10549
    VERTEX_AI = "vertexai"  # GH#9009
    BEDROCK = "bedrock"  # GH#9010


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
    "ArchitectureFamily",
    "ProviderType",
    "LLMType",
]
