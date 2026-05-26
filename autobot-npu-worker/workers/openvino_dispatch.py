#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Architecture-aware OpenVINO inference dispatcher.

Dispatches model-load and inference requests to the correct OpenVINO code path
based on the model's architecture_family field (GH#7352).

Supported families track the enum defined in llm_interface_pkg/types.py
(GH#7347): transformer, state_space, linear_attention, hybrid.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "ArchitectureFamily",
    "UnsupportedArchitectureError",
    "get_inference_config",
    "SUPPORTED_FAMILIES",
]


class ArchitectureFamily(str, Enum):
    """Architecture families understood by the NPU worker."""

    TRANSFORMER = "transformer"
    STATE_SPACE = "state_space"
    LINEAR_ATTENTION = "linear_attention"
    HYBRID = "hybrid"


# Families for which an OpenVINO inference path exists on this worker.
# state_space / linear_attention / hybrid paths are placeholders until the
# corresponding OpenVINO SSM kernel work lands (out of scope for GH#7352).
SUPPORTED_FAMILIES: frozenset[str] = frozenset({ArchitectureFamily.TRANSFORMER})


class UnsupportedArchitectureError(ValueError):
    """Raised when the worker has no inference path for the requested family."""

    def __init__(self, family: str) -> None:
        self.family = family
        super().__init__(
            f"architecture_family '{family}' is not supported on this OpenVINO worker. "
            f"Supported families: {sorted(SUPPORTED_FAMILIES)}. "
            "Support for state_space / linear_attention / hybrid requires an OpenVINO "
            "SSM kernel upgrade — see GH#7352 for the planned follow-up."
        )


def get_inference_config(
    model_id: str,
    architecture_family: Optional[str],
    device: str = "CPU",
) -> Dict[str, Any]:
    """
    Return the OpenVINO inference configuration for a given model and family.

    Raises UnsupportedArchitectureError for families without an inference path.

    Args:
        model_id: Opaque model identifier forwarded to OpenVINO.
        architecture_family: One of ArchitectureFamily values, or None (defaults
            to transformer for backward compatibility).
        device: Target OpenVINO device string (e.g. "CPU", "NPU", "GPU").

    Returns:
        Dict with keys: model_id, device, architecture_family, inference_backend.
    """
    resolved_family = (architecture_family or ArchitectureFamily.TRANSFORMER).lower()

    if resolved_family not in SUPPORTED_FAMILIES:
        raise UnsupportedArchitectureError(resolved_family)

    # Currently only the transformer path exists; this branch is where
    # state_space / linear_attention / hybrid paths will be added when
    # OpenVINO SSM kernel support lands.
    inference_backend = _select_backend(resolved_family)

    logger.debug(
        "architecture_family=%s → inference_backend=%s for model=%s on device=%s",
        resolved_family,
        inference_backend,
        model_id,
        device,
    )

    return {
        "model_id": model_id,
        "device": device,
        "architecture_family": resolved_family,
        "inference_backend": inference_backend,
    }


def _select_backend(family: str) -> str:
    """Map a validated architecture family to an OpenVINO backend identifier."""
    if family == ArchitectureFamily.TRANSFORMER:
        return "openvino_transformer"
    # Unreachable until SUPPORTED_FAMILIES is expanded, but explicit for clarity.
    raise UnsupportedArchitectureError(family)
