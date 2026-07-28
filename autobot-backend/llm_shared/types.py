# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LLM Interface Types - Enums and constants for LLM operations.

Extracted from llm_interface.py as part of Issue #381 god class refactoring.
"""

from enum import Enum

from autobot_shared.status_enums import LLMProvider as _CanonicalLLMProvider


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


#: Supported LLM providers.
#:
#: Single canonical source of truth (#12661): this used to be its own
#: ``Enum`` and disagreed with ``autobot_shared.status_enums.LLMProvider``
#: and ``services.llm_cost_tracker.LLMProvider``. All three member sets are
#: now unioned onto the canonical enum in ``autobot_shared/status_enums.py``;
#: this name is a thin alias so every existing ``ProviderType.X`` call site
#: (``ProviderType.OLLAMA``, ``ProviderType.VLLM``, ...) keeps working
#: unchanged, and every ``.value`` string is preserved exactly.
ProviderType = _CanonicalLLMProvider


class LLMType(str, Enum):
    """Types of LLM usage contexts.

    Subclasses ``str`` (#11019) so a member is interchangeable with its string
    value everywhere — ``LLMType.EXTRACTION == "extraction"``, dict lookups keyed
    by the raw string still resolve, and legacy call sites passing the string keep
    working — while call sites can adopt ``LLMType.X`` for author-time typo safety.
    """

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
