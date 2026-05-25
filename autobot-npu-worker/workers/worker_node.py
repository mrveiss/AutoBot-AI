# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU Worker Node — HTTP entrypoint for pipeline forward-pass requests.

Handles:
  POST /partial_forward  — layer-range inference (MVA-1098)
  GET  /capabilities     — reports max_layers and per-layer VRAM cost

The last worker in the pipeline receives hidden_state from upstream layers and
produces token logits; it then runs argmax to yield token IDs.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Sentinel value returned by detect_capabilities when NPU is unavailable
_VRAM_BYTES_PER_LAYER_FALLBACK = 256 * 1024 * 1024  # 256 MB
_MAX_LAYERS_FALLBACK = 32


# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------


def detect_capabilities(model_registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return this worker's hardware capabilities for shard planning.

    Returns a dict with:
        max_layers          — maximum number of model layers this worker can hold
        vram_bytes_per_layer — estimated VRAM cost per transformer layer in bytes
        device              — hardware device label (e.g. "NPU", "CPU")

    Args:
        model_registry: Optional mapping of loaded models; if provided, the
            per-layer cost reflects the heaviest currently-loaded model.
    """
    try:
        import openvino.runtime as ov  # type: ignore[import]

        core = ov.Core()
        devices = core.available_devices
        npu_devices = [d for d in devices if "NPU" in d.upper()]
        if npu_devices:
            device = npu_devices[0]
            try:
                total_vram = core.get_property(device, "DEVICE_TOTAL_MEMORY")
            except Exception:
                total_vram = None
        else:
            device = "CPU"
            total_vram = None
    except Exception:
        device = "CPU"
        total_vram = None

    vram_bytes_per_layer = _estimate_vram_per_layer(model_registry)

    if total_vram and total_vram > 0:
        max_layers = max(1, total_vram // vram_bytes_per_layer)
    else:
        max_layers = _MAX_LAYERS_FALLBACK

    return {
        "max_layers": int(max_layers),
        "vram_bytes_per_layer": int(vram_bytes_per_layer),
        "device": device,
    }


def _estimate_vram_per_layer(model_registry: Optional[Dict[str, Any]]) -> int:
    """Estimate per-layer VRAM in bytes from the loaded model registry."""
    if not model_registry:
        return _VRAM_BYTES_PER_LAYER_FALLBACK

    costs = []
    for model_meta in model_registry.values():
        total_bytes = model_meta.get("total_bytes", 0)
        num_layers = model_meta.get("num_layers", 0)
        if total_bytes and num_layers:
            costs.append(total_bytes // num_layers)

    return int(sum(costs) / len(costs)) if costs else _VRAM_BYTES_PER_LAYER_FALLBACK


# ---------------------------------------------------------------------------
# Partial-forward handler
# ---------------------------------------------------------------------------


def handle_partial_forward(
    model_id: str,
    layer_range: Tuple[int, int],
    hidden_state_in: Any,
    model_loader: Any,
    *,
    is_last_worker: bool = False,
) -> Dict[str, Any]:
    """Run a partial forward pass over a sub-range of model layers.

    Args:
        model_id: Identifier of the model to run.
        layer_range: (start, end) inclusive layer indices to execute.
        hidden_state_in: Activations from the previous worker (or token
            embeddings for the first worker).
        model_loader: Object with a ``get_layers(model_id)`` method that
            returns the ordered list of callable layer objects.
        is_last_worker: When True the output is treated as token logits and
            argmax is applied to produce token IDs.

    Returns:
        Dict with key ``hidden_state_out`` (activations) or ``token_ids``
        (list of ints) when ``is_last_worker`` is True.
    """
    layer_start, layer_end = layer_range
    if layer_start < 0 or layer_end < layer_start:
        raise ValueError(
            f"Invalid layer_range ({layer_start}, {layer_end}): "
            "must satisfy 0 <= start <= end."
        )

    layers = model_loader.get_layers(model_id)
    if layer_end >= len(layers):
        raise ValueError(
            f"layer_end={layer_end} exceeds model depth {len(layers) - 1}."
        )

    hidden = hidden_state_in
    for idx in range(layer_start, layer_end + 1):
        hidden = layers[idx](hidden)
        logger.debug("worker_node: ran layer %d for model %s", idx, model_id)

    if is_last_worker:
        token_ids = _logits_to_token_ids(hidden)
        return {"token_ids": token_ids}

    return {"hidden_state_out": hidden}


def _logits_to_token_ids(logits: Any) -> List[int]:
    """Convert logit tensor to token IDs via argmax.

    Supports numpy arrays, torch tensors, and plain lists.
    """
    try:
        import numpy as np  # type: ignore[import]

        arr = np.asarray(logits)
        if arr.ndim == 1:
            return [int(arr.argmax())]
        # Shape: (batch, vocab) or (batch, seq, vocab)
        if arr.ndim == 2:
            return arr.argmax(axis=-1).tolist()
        if arr.ndim == 3:
            return arr[:, -1, :].argmax(axis=-1).tolist()
        return [int(arr.argmax())]
    except Exception:
        pass

    try:
        import torch  # type: ignore[import]

        t = torch.as_tensor(logits)
        return t.argmax(dim=-1).flatten().tolist()
    except Exception:
        pass

    # Last resort: plain list
    if isinstance(logits, list):
        flat = logits if not isinstance(logits[0], list) else logits[0]
        return [flat.index(max(flat))]

    raise TypeError(f"Cannot convert logits of type {type(logits)} to token IDs.")
