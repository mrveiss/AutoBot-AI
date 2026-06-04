#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Architecture-aware OpenVINO inference dispatcher.

Dispatches model-load and inference requests to the correct OpenVINO code path
based on the model's architecture_family field (GH#7352, MVA-1383).

Supported families track the enum defined in llm_interface_pkg/types.py
(GH#7347): transformer, ssm, linear_attention, hybrid.

SSM path (Mamba/S4 models) is gated behind the NPU_SSM_ENABLED env-var
feature flag (default off until validated in staging).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, FrozenSet, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "ArchitectureFamily",
    "InferenceEngine",
    "UnsupportedArchitectureError",
    "get_inference_config",
    "get_inference_engine",
    "is_npu_ssm_enabled",
    "SUPPORTED_FAMILIES",
]


class ArchitectureFamily(str, Enum):
    """Architecture families understood by the NPU worker."""

    TRANSFORMER = "transformer"
    SSM = "ssm"
    LINEAR_ATTENTION = "linear_attention"
    HYBRID = "hybrid"


def is_npu_ssm_enabled() -> bool:
    """Return True when the NPU_SSM_ENABLED feature flag is set.

    Reads the NPU_SSM_ENABLED env var at call time so tests can patch it
    without re-importing the module.  Default is off (False).
    """
    return os.environ.get("NPU_SSM_ENABLED", "").lower() in ("1", "true", "yes")


def _get_supported_families() -> FrozenSet[str]:
    """Return the set of currently supported architecture families.

    Computed at call time so the SSM feature flag is respected without a
    module reload.
    """
    families = {ArchitectureFamily.TRANSFORMER}
    if is_npu_ssm_enabled():
        families.add(ArchitectureFamily.SSM)
    return frozenset(families)


# Module-level constant exposed for introspection; callers that need runtime
# accuracy should use _get_supported_families() instead.
SUPPORTED_FAMILIES: FrozenSet[str] = frozenset({ArchitectureFamily.TRANSFORMER})


class UnsupportedArchitectureError(ValueError):
    """Raised when the worker has no inference path for the requested family."""

    def __init__(self, family: str) -> None:
        self.family = family
        super().__init__(
            f"architecture_family '{family}' is not supported on this OpenVINO worker. "
            f"Supported families: {sorted(_get_supported_families())}. "
            "SSM path requires NPU_SSM_ENABLED=true and validated OpenVINO SSM kernels "
            "— see GH#7352 / MVA-1383 for details."
        )


@dataclass(frozen=True)
class InferenceEngine:
    """Resolved inference engine for a model/device/family combination.

    Produced by get_inference_engine(); carry this into handle_partial_forward
    so each forward pass uses the architecture-correct OpenVINO backend.

    Attributes:
        model_id: Opaque model identifier.
        device: Target OpenVINO device (e.g. "CPU", "NPU", "GPU").
        architecture_family: Resolved family string (always lowercase).
        inference_backend: Backend identifier selected by the dispatcher
            (e.g. "openvino_transformer", "openvino_ssm").
        run_layer: Callable that executes one model layer.  Injected at
            construction time; defaults to a direct call so the engine is
            usable without OpenVINO installed (tests, CPU-only workers).
    """

    model_id: str
    device: str
    architecture_family: str
    inference_backend: str
    run_layer: Callable[[Any, Any], Any]

    def forward(self, layers: List[Any], hidden: Any) -> Any:
        """Run *layers* sequentially, forwarding hidden state through each."""
        for layer in layers:
            hidden = self.run_layer(layer, hidden)
        return hidden


def _default_run_layer(layer: Any, hidden: Any) -> Any:
    """Call *layer* directly — works for any callable layer object."""
    return layer(hidden)


def get_inference_engine(
    model_id: str,
    architecture_family: Optional[str],
    device: str = "CPU",
    *,
    run_layer: Optional[Callable[[Any, Any], Any]] = None,
) -> InferenceEngine:
    """Return a ready-to-use InferenceEngine for the given model and family.

    Validates *architecture_family* via get_inference_config and packages the
    result into an InferenceEngine.  Callers should call engine.forward() (or
    engine.run_layer()) instead of dispatching manually so the backend
    selection stays in one place (GH#8690).

    Args:
        model_id: Opaque model identifier.
        architecture_family: One of ArchitectureFamily values, or None
            (defaults to transformer for backward compatibility).
        device: Target OpenVINO device string (e.g. "CPU", "NPU", "GPU").
        run_layer: Optional callable ``(layer, hidden) -> hidden`` that
            executes a single model layer.  Defaults to a direct call, which
            is correct for both real OpenVINO layer objects and mock layers
            used in tests.

    Returns:
        InferenceEngine with all fields populated.

    Raises:
        UnsupportedArchitectureError: When no inference path exists for the
            requested family (including ssm when NPU_SSM_ENABLED is not set).
    """
    cfg = get_inference_config(model_id, architecture_family, device)
    engine = InferenceEngine(
        model_id=cfg["model_id"],
        device=cfg["device"],
        architecture_family=cfg["architecture_family"],
        inference_backend=cfg["inference_backend"],
        run_layer=run_layer if run_layer is not None else _default_run_layer,
    )
    logger.debug(
        "get_inference_engine: model=%s device=%s family=%s backend=%s",
        engine.model_id,
        engine.device,
        engine.architecture_family,
        engine.inference_backend,
    )
    return engine


def get_inference_config(
    model_id: str,
    architecture_family: Optional[str],
    device: str = "CPU",
) -> Dict[str, Any]:
    """
    Return the OpenVINO inference configuration for a given model and family.

    Raises UnsupportedArchitectureError for families without an inference path.
    The SSM path (family="ssm") is only available when NPU_SSM_ENABLED=true.

    Args:
        model_id: Opaque model identifier forwarded to OpenVINO.
        architecture_family: One of ArchitectureFamily values, or None (defaults
            to transformer for backward compatibility).
        device: Target OpenVINO device string (e.g. "CPU", "NPU", "GPU").

    Returns:
        Dict with keys: model_id, device, architecture_family, inference_backend.
    """
    resolved_family = (architecture_family or ArchitectureFamily.TRANSFORMER).lower()

    if resolved_family not in _get_supported_families():
        raise UnsupportedArchitectureError(resolved_family)

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
    if family == ArchitectureFamily.SSM:
        return "openvino_ssm"
    # linear_attention and hybrid are not yet supported; this is unreachable
    # until SUPPORTED_FAMILIES is expanded for those families.
    raise UnsupportedArchitectureError(family)
