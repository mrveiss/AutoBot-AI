# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Model taxonomies shared by the backend and the NPU worker (#13049 C1).

``ArchitectureFamily`` lives here once; ``llm_shared.types`` re-exports it and the
NPU worker's ``openvino_dispatch`` imports it. Which members a given consumer
supports is that consumer's explicit decision, not a separate enum.
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


class UnsupportedArchitectureError(ValueError):
    """A consumer has no code path for a known architecture family (#13049 C1).

    The one definition shared by the NPU worker dispatcher and the backend layer
    layout. ``family`` is the offending family or model_type; ``message``
    overrides the default text when the consumer can say what it does support.
    """

    def __init__(self, family: str, message: "str | None" = None) -> None:
        self.family = family
        super().__init__(message or f"architecture '{family}' is not supported by this consumer")
