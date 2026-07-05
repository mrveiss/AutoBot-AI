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
    """Model architecture family — governs attention backend, NPU dispatch, and
    context-window policy.

    Single canonical source of truth (#10892): previously duplicated as a
    separate enum in ``model_param_registry`` with a divergent member name
    (``SSM``).  Both classes are now this one.

    Issue #7347: positive family signal replacing substring-match heuristics.

    State-space serialized values: the state-space family has two live,
    persisted ``.value`` spellings across the codebase — ``"state_space"``
    (attention-backend dispatch + structured logs) and ``"ssm"`` (YAML
    ``architecture_family`` entries, NPU registry, and tiered long-context
    routing).  Both are retained as distinct members so value-based matching
    against either persisted string keeps working; ``STATE_SPACE`` is the
    canonical descriptive name and both route to the SSM handler.
    """

    TRANSFORMER = "transformer"
    STATE_SPACE = "state_space"  # Mamba / S4 family — canonical name
    SSM = "ssm"  # Persisted alias value for state-space (YAML/registry/routing)
    LINEAR_ATTENTION = "linear_attention"
    HYBRID = "hybrid"  # Jamba-style mixed architectures
    MOE = "moe"  # Mixture-of-Experts (from NPU registry, #10892)


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
