# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Empty-weight model inspection for hardware routing decisions.

Uses HuggingFace Accelerate's ``init_empty_weights()`` context manager to load
a model's *architecture* onto the meta device at zero memory cost.  The model
skeleton is instantiated via ``AutoModelForCausalLM.from_config()`` inside the
context so that no real tensors are allocated.  Parameter counts are read directly
from the skeleton with ``sum(p.numel() for p in model.parameters())``, giving
accurate counts for GQA (Llama 2/3, Mistral) and MoE (Mixtral) architectures.

Architecture attributes (layer count, hidden size, attention heads, parameter count)
are used by hardware routing to decide whether a model fits in available VRAM before
any weights are loaded.

Results are cached in a process-level dict with TTL to avoid repeated HuggingFace
Hub round-trips.

Issue #1945: Empty-weight model inspection for hardware routing.
Issue #3186: Actually call init_empty_weights() for accurate param counts.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from constants.ttl_constants import TTL_1_HOUR

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Bytes per float32 parameter (used for size estimation).
_BYTES_PER_FP32: int = 4

#: TTL for cached ModelInfo entries (seconds).
_CACHE_TTL_SECONDS: int = TTL_1_HOUR

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

#: Module-level cache: model_name -> (ModelInfo, expiry_timestamp)
_cache: Dict[str, tuple] = {}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ModelInfo:
    """
    Architecture metadata extracted from a model config at zero memory cost.

    Attributes:
        num_layers: Number of transformer decoder/encoder layers.
        hidden_size: Hidden dimension of the model.
        num_attention_heads: Number of attention heads.
        param_count: Estimated total parameter count.
        estimated_size_gb: Estimated fp32 weight size in gigabytes.
    """

    num_layers: int
    hidden_size: int
    num_attention_heads: int
    param_count: int
    estimated_size_gb: float


# ---------------------------------------------------------------------------
# Lazy import helpers
# ---------------------------------------------------------------------------


def _import_transformers() -> Any:
    """Lazily import transformers; raises ImportError with guidance if absent."""
    try:
        import transformers  # noqa: PLC0415

        return transformers
    except ImportError as exc:
        raise ImportError(
            "transformers is required for model inspection. " "Install with: pip install transformers"
        ) from exc


def _import_accelerate() -> Any:
    """Lazily import accelerate; raises ImportError with guidance if absent."""
    try:
        import accelerate  # noqa: PLC0415

        return accelerate
    except ImportError as exc:
        raise ImportError(
            "accelerate is required for empty-weight model inspection. " "Install with: pip install accelerate"
        ) from exc


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_get(model_name: str) -> ModelInfo | None:
    """Return cached ModelInfo if present and unexpired, else None."""
    entry = _cache.get(model_name)
    if entry is None:
        return None
    info, expiry = entry
    if time.monotonic() > expiry:
        del _cache[model_name]
        return None
    return info


def _cache_put(model_name: str, info: ModelInfo) -> None:
    """Store ModelInfo in cache with TTL."""
    _cache[model_name] = (info, time.monotonic() + _CACHE_TTL_SECONDS)


# ---------------------------------------------------------------------------
# Config extraction helpers
# ---------------------------------------------------------------------------


def _extract_from_config(cfg: Any, param_count_override: int | None = None) -> ModelInfo:
    """
    Build a ModelInfo from a transformers PretrainedConfig object.

    Handles the two common attribute layouts (decoder-only and encoder-decoder).

    Args:
        cfg: A transformers PretrainedConfig (or any object with matching attrs).
        param_count_override: When provided (e.g. from an empty-weight skeleton),
            this value is used instead of the formula-based estimate.
    """
    num_layers = (
        getattr(cfg, "num_hidden_layers", None)
        or getattr(cfg, "num_layers", None)
        or getattr(cfg, "n_layer", None)
        or 0
    )
    hidden_size = (
        getattr(cfg, "hidden_size", None) or getattr(cfg, "d_model", None) or getattr(cfg, "n_embd", None) or 0
    )
    num_attention_heads = getattr(cfg, "num_attention_heads", None) or getattr(cfg, "n_head", None) or 0
    vocab_size = getattr(cfg, "vocab_size", 0) or 0

    if param_count_override is not None:
        param_count = param_count_override
    else:
        param_count = _estimate_param_count(num_layers, hidden_size, vocab_size)
    estimated_size_gb = (param_count * _BYTES_PER_FP32) / (1024**3)

    return ModelInfo(
        num_layers=num_layers,
        hidden_size=hidden_size,
        num_attention_heads=num_attention_heads,
        param_count=param_count,
        estimated_size_gb=estimated_size_gb,
    )


def _estimate_param_count(num_layers: int, hidden_size: int, vocab_size: int) -> int:
    """
    Rough parameter count estimate from architectural dimensions.

    Uses the standard transformer block formula:
      - Embedding: vocab_size * hidden_size
      - Per layer: 4 * hidden_size^2  (attention) + 8 * hidden_size^2 (MLP)

    This formula underestimates GQA (Llama 2/3, Mistral) and MoE (Mixtral)
    models.  It is only used as a fallback when ``init_empty_weights()`` fails.
    """
    if num_layers == 0 or hidden_size == 0:
        return 0
    embedding_params = vocab_size * hidden_size
    per_layer_params = 12 * (hidden_size**2)
    return embedding_params + num_layers * per_layer_params


def _count_params_via_skeleton(cfg: Any, transformers: Any, accelerate: Any) -> int | None:
    """
    Instantiate an empty-weight model skeleton and return its exact param count.

    Uses ``accelerate.init_empty_weights()`` so no real tensors are allocated —
    all parameters live on the PyTorch meta device.  Returns ``None`` on any
    failure so the caller can fall back to the formula-based estimate.

    Args:
        cfg: A transformers PretrainedConfig.
        transformers: The transformers module.
        accelerate: The accelerate module.

    Returns:
        Total parameter count from the skeleton, or None on failure.
    """
    try:
        with accelerate.init_empty_weights():
            model = transformers.AutoModelForCausalLM.from_config(cfg)
        return sum(p.numel() for p in model.parameters())
    except Exception as exc:  # noqa: BLE001
        logger.debug("model_inspector: skeleton param count failed — %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def inspect_model(model_name: str) -> ModelInfo | None:
    """
    Inspect a model's architecture at zero memory cost.

    Loads only the model config (via HuggingFace Hub) and then initialises an
    empty-weight skeleton using ``accelerate.init_empty_weights()``.  No actual
    weights are downloaded or loaded into RAM.

    Results are cached for ``_CACHE_TTL_SECONDS`` seconds.  Returns ``None``
    when the model config is unavailable (e.g. Ollama-only models).

    Args:
        model_name: HuggingFace model ID or local path.

    Returns:
        ModelInfo with architecture details, or None on any failure.
    """
    cached = _cache_get(model_name)
    if cached is not None:
        logger.debug("model_inspector: cache hit for %s", model_name)
        return cached

    info = _inspect_via_config(model_name)
    if info is not None:
        _cache_put(model_name, info)
    return info


def _inspect_via_config(model_name: str) -> ModelInfo | None:
    """
    Fetch model config, build an empty-weight skeleton, and return ModelInfo.

    Separating this from ``inspect_model`` keeps the public function's
    caching logic and this function each under 30 lines.

    Tries to get exact param counts via ``init_empty_weights()``; falls back to
    the formula-based estimate if skeleton instantiation fails.
    """
    try:
        transformers = _import_transformers()
        accelerate = _import_accelerate()
    except ImportError as exc:
        logger.warning("model_inspector: dependency missing for %s — %s", model_name, exc)
        return None

    try:
        cfg = transformers.AutoConfig.from_pretrained(
            model_name, resume_download=True
        )  # nosec B615 - HuggingFace model loaded by name; revision pinning managed operationally
        param_count = _count_params_via_skeleton(cfg, transformers, accelerate)
        if param_count is None:
            logger.debug("model_inspector: using formula fallback for %s", model_name)
        info = _extract_from_config(cfg, param_count_override=param_count)
        logger.info(
            "model_inspector: %s — layers=%d hidden=%d heads=%d params=~%dM size=~%.1fGB",
            model_name,
            info.num_layers,
            info.hidden_size,
            info.num_attention_heads,
            info.param_count // 1_000_000,
            info.estimated_size_gb,
        )
        return info
    except Exception as exc:  # noqa: BLE001
        logger.debug("model_inspector: could not inspect %s — %s", model_name, exc)
        return None


def clear_cache() -> None:
    """Clear the model inspection cache (primarily for testing)."""
    _cache.clear()


__all__ = [
    "ModelInfo",
    "inspect_model",
    "clear_cache",
]
