# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Layer-aligned KV cache management for sequential layer processing.

During layer-by-layer inference the key and value tensors for every layer must
persist across the entire forward pass AND across generation steps.  This module
provides explicit, per-layer storage with a VRAM budget calculator targeted at
the RTX 4070 (8 GB VRAM).

Distinct from GrowingKVCache (flash_attention.py) which stores a single packed
[batch, seq, 2, heads, dim] tensor for the flash-attention forward pass.
This module stores independent (k, v) tensor pairs keyed by layer index,
matching the access pattern of layer-by-layer inference loops.

Issue #1964: Layer-aligned KV cache management for sequential layer processing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Tuple

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    import torch

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lazy torch import — module degrades gracefully without it
# ---------------------------------------------------------------------------
_torch = None
_torch_checked = False


def _get_torch():
    """Return the torch module, importing lazily on first call."""
    global _torch, _torch_checked  # noqa: PLW0603
    if not _torch_checked:
        _torch_checked = True
        try:
            import torch as _t

            _torch = _t
        except (ImportError, RuntimeError):
            _torch = None
    return _torch


# ---------------------------------------------------------------------------
# Constants — RTX 4070 reference values
# ---------------------------------------------------------------------------

#: Total VRAM on the RTX 4070 (bytes).
RTX_4070_VRAM_BYTES: int = 8 * 1024 * 1024 * 1024

#: Recommended fraction of RTX 4070 VRAM to budget for KV caches.
#: Leaves headroom for model weights, activations, and framework overhead.
RTX_4070_KV_CACHE_FRACTION: float = 0.35

#: Bytes per element for supported dtypes.
_DTYPE_BYTES: Dict[str, int] = {
    "fp16": 2,
    "bf16": 2,
    "fp32": 4,
    "float16": 2,
    "bfloat16": 2,
    "float32": 4,
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class KVCacheConfig:
    """Configuration for a layer-aligned KV cache.

    Issue #1964.

    Attributes:
        num_layers: Number of transformer layers (depth of the model).
        num_heads: Number of key/value attention heads per layer.
        head_dim: Dimension of each attention head.
        max_seq_len: Maximum sequence length the cache must accommodate.
        dtype: Element dtype as a string — "fp16", "bf16", or "fp32".
        device: Torch device string, e.g. "cuda", "cuda:0", "cpu".
        batch_size: Batch size the cache is allocated for.
    """

    num_layers: int
    num_heads: int
    head_dim: int
    max_seq_len: int
    dtype: str = "fp16"
    device: str = "cpu"
    batch_size: int = 1

    def __post_init__(self) -> None:
        """Validate configuration fields."""
        if self.num_layers < 1:
            raise ValueError(f"num_layers must be >= 1, got {self.num_layers}")
        if self.num_heads < 1:
            raise ValueError(f"num_heads must be >= 1, got {self.num_heads}")
        if self.head_dim < 1:
            raise ValueError(f"head_dim must be >= 1, got {self.head_dim}")
        if self.max_seq_len < 1:
            raise ValueError(f"max_seq_len must be >= 1, got {self.max_seq_len}")
        if self.batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {self.batch_size}")
        if self.dtype not in _DTYPE_BYTES:
            raise ValueError(f"Unsupported dtype '{self.dtype}'. " f"Choose from: {sorted(_DTYPE_BYTES)}")

    @property
    def dtype_bytes(self) -> int:
        """Bytes per element for the configured dtype."""
        return _DTYPE_BYTES[self.dtype]


# ---------------------------------------------------------------------------
# Per-layer cache storage
# ---------------------------------------------------------------------------


@dataclass
class _LayerEntry:
    """Internal storage for a single layer's (k, v) tensors.

    Attributes:
        k: Key cache tensor [batch, seq_len, num_heads, head_dim] or None.
        v: Value cache tensor [batch, seq_len, num_heads, head_dim] or None.
        filled_len: Number of valid positions written into the cache.
    """

    k: "torch.Tensor" | None = None  # noqa: F821
    v: "torch.Tensor" | None = None  # noqa: F821
    filled_len: int = 0


class LayerKVCache:
    """Per-layer KV cache for sequential layer processing.

    Stores independent (k, v) tensor pairs for each transformer layer.
    Supports incremental updates across generation steps.

    Issue #1964.

    Args:
        config: Cache configuration (layers, heads, head_dim, seq_len, dtype, device).
    """

    def __init__(self, config: KVCacheConfig) -> None:
        self._config = config
        self._entries: Dict[int, _LayerEntry] = {}
        logger.debug(
            "LayerKVCache created: %d layers, %d heads, head_dim=%d, max_seq=%d, dtype=%s",
            config.num_layers,
            config.num_heads,
            config.head_dim,
            config.max_seq_len,
            config.dtype,
        )

    @property
    def config(self) -> KVCacheConfig:
        """Cache configuration."""
        return self._config

    @property
    def num_filled_layers(self) -> int:
        """Number of layers that have at least one cached position."""
        return sum(1 for e in self._entries.values() if e.filled_len > 0)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def get(self, layer_idx: int) -> Tuple["torch.Tensor", "torch.Tensor"] | None:
        """Return the cached (k, v) tensors for a layer, or None.

        Only the filled portion is returned — trailing padding is not exposed.

        Issue #1964.

        Args:
            layer_idx: Zero-based transformer layer index.

        Returns:
            Tuple (k, v) each shaped [batch, filled_len, num_heads, head_dim],
            or None if this layer has no cached data yet.
        """
        entry = self._entries.get(layer_idx)
        if entry is None or entry.k is None or entry.filled_len == 0:
            return None
        k_view = entry.k[:, : entry.filled_len, :, :]
        v_view = entry.v[:, : entry.filled_len, :, :]
        return k_view, v_view

    def update(
        self,
        layer_idx: int,
        new_k: "torch.Tensor",
        new_v: "torch.Tensor",
    ) -> Tuple["torch.Tensor", "torch.Tensor"]:
        """Append new (k, v) positions to the cache for a layer.

        If the layer has no existing cache, it is allocated now with capacity
        equal to ``config.max_seq_len``.  Subsequent calls concatenate along
        the sequence dimension.

        Issue #1964.

        Args:
            layer_idx: Zero-based transformer layer index.
            new_k: New key tensor [batch, new_seq, num_heads, head_dim].
            new_v: New value tensor [batch, new_seq, num_heads, head_dim].

        Returns:
            Updated (k, v) including all previously cached positions,
            each shaped [batch, total_seq, num_heads, head_dim].

        Raises:
            RuntimeError: If PyTorch is not available.
            ValueError: If new_k/new_v shapes are inconsistent with the config.
        """
        torch = _get_torch()
        if torch is None:
            raise RuntimeError("PyTorch is required for LayerKVCache.update()")

        self._validate_kv_shapes(layer_idx, new_k, new_v)

        entry = self._entries.get(layer_idx)
        if entry is None:
            entry = _LayerEntry()
            self._entries[layer_idx] = entry

        new_seq = new_k.shape[1]

        if entry.k is None:
            entry.k, entry.v = self._allocate_layer_tensors(torch, new_k)

        self._write_to_entry(entry, new_k, new_v, new_seq)

        logger.debug(
            "LayerKVCache update: layer=%d new_seq=%d total_seq=%d",
            layer_idx,
            new_seq,
            entry.filled_len,
        )

        return (
            entry.k[:, : entry.filled_len, :, :],
            entry.v[:, : entry.filled_len, :, :],
        )

    def trim_to_length(self, max_len: int) -> None:
        """Trim all layer caches to at most max_len filled positions.

        Useful for sliding-window attention or when sequence length exceeds
        a target budget.  The underlying tensor allocation is unchanged —
        only the filled_len pointer is moved back.

        Issue #1964.

        Args:
            max_len: Maximum number of positions to retain per layer.
        """
        if max_len < 0:
            raise ValueError(f"max_len must be >= 0, got {max_len}")
        trimmed_layers = 0
        for layer_idx, entry in self._entries.items():
            if entry.filled_len > max_len:
                entry.filled_len = max_len
                trimmed_layers += 1
        if trimmed_layers > 0:
            logger.debug(
                "LayerKVCache trimmed %d layers to max_len=%d",
                trimmed_layers,
                max_len,
            )

    def clear(self) -> None:
        """Release all cached tensors and reset filled lengths.

        Issue #1964.
        """
        self._entries.clear()
        logger.debug("LayerKVCache cleared")

    def memory_usage_bytes(self) -> int:
        """Return the total allocated memory across all layer tensors (bytes).

        Counts both the k and v tensors for every layer that has been
        allocated, regardless of how many positions are filled.

        Issue #1964.

        Returns:
            Total bytes currently allocated for this cache.
        """
        total = 0
        for entry in self._entries.values():
            if entry.k is not None:
                total += _tensor_bytes(entry.k)
            if entry.v is not None:
                total += _tensor_bytes(entry.v)
        return total

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_kv_shapes(
        self,
        layer_idx: int,
        new_k: "torch.Tensor",
        new_v: "torch.Tensor",
    ) -> None:
        """Raise ValueError if new_k / new_v shapes violate the config.

        Issue #1964: Validates batch, num_heads, and head_dim dimensions.
        Only new_seq is allowed to vary.
        """
        cfg = self._config
        for name, tensor in (("new_k", new_k), ("new_v", new_v)):
            if tensor.ndim != 4:
                raise ValueError(
                    f"{name} must be 4D [batch, seq, heads, head_dim], " f"got {tensor.ndim}D for layer {layer_idx}"
                )
            b, _seq, h, d = tensor.shape
            if b != cfg.batch_size:
                raise ValueError(
                    f"{name} batch size {b} != config batch_size {cfg.batch_size} " f"for layer {layer_idx}"
                )
            if h != cfg.num_heads:
                raise ValueError(f"{name} num_heads {h} != config num_heads {cfg.num_heads} " f"for layer {layer_idx}")
            if d != cfg.head_dim:
                raise ValueError(f"{name} head_dim {d} != config head_dim {cfg.head_dim} " f"for layer {layer_idx}")

    def _allocate_layer_tensors(
        self,
        torch,
        reference_kv: "torch.Tensor",
    ) -> Tuple["torch.Tensor", "torch.Tensor"]:
        """Allocate zero-filled k and v tensors for a layer.

        Capacity is config.max_seq_len positions.

        Issue #1964.
        """
        cfg = self._config
        shape = (cfg.batch_size, cfg.max_seq_len, cfg.num_heads, cfg.head_dim)
        dtype = reference_kv.dtype
        device = reference_kv.device
        k = torch.zeros(shape, dtype=dtype, device=device)
        v = torch.zeros(shape, dtype=dtype, device=device)
        return k, v

    def _write_to_entry(
        self,
        entry: _LayerEntry,
        new_k: "torch.Tensor",
        new_v: "torch.Tensor",
        new_seq: int,
    ) -> None:
        """Write new_k/new_v into entry at the current filled position.

        Issue #1964: Raises ValueError if the write would overflow max_seq_len.
        """
        start = entry.filled_len
        end = start + new_seq
        if end > self._config.max_seq_len:
            raise ValueError(
                f"KV cache overflow: current={start}, adding={new_seq}, " f"max_seq_len={self._config.max_seq_len}"
            )
        entry.k[:, start:end, :, :] = new_k
        entry.v[:, start:end, :, :] = new_v
        entry.filled_len = end


# ---------------------------------------------------------------------------
# Cache manager — memory budgeting and factory
# ---------------------------------------------------------------------------


class KVCacheManager:
    """Factory and memory budget calculator for LayerKVCache instances.

    Provides helpers for the RTX 4070 (8 GB VRAM) scenario to determine
    how many sequence positions can fit within a given VRAM budget.

    Issue #1964.
    """

    def create_cache(self, config: KVCacheConfig) -> LayerKVCache:
        """Create a LayerKVCache from the given configuration.

        Issue #1964.

        Args:
            config: Fully specified KV cache configuration.

        Returns:
            A new, empty LayerKVCache ready for use.
        """
        estimated = self.estimate_memory(config)
        logger.info(
            "Creating KV cache: layers=%d heads=%d head_dim=%d max_seq=%d " "dtype=%s estimated_mb=%.1f",
            config.num_layers,
            config.num_heads,
            config.head_dim,
            config.max_seq_len,
            config.dtype,
            estimated / (1024 * 1024),
        )
        return LayerKVCache(config)

    def estimate_memory(self, config: KVCacheConfig) -> int:
        """Estimate peak VRAM for a fully populated LayerKVCache (bytes).

        Formula::

            2 (k + v) * num_layers * batch_size * max_seq_len
            * num_heads * head_dim * dtype_bytes

        Issue #1964.

        Args:
            config: Cache configuration.

        Returns:
            Estimated bytes needed when all layers are fully populated.
        """
        return _compute_cache_bytes(
            num_layers=config.num_layers,
            batch_size=config.batch_size,
            max_seq_len=config.max_seq_len,
            num_heads=config.num_heads,
            head_dim=config.head_dim,
            dtype_bytes=config.dtype_bytes,
        )

    def max_sequence_length(
        self,
        vram_budget_gb: float,
        config: KVCacheConfig,
    ) -> int:
        """Calculate the maximum sequence length that fits in a VRAM budget.

        Uses the same formula as estimate_memory(), solved for max_seq_len.
        Returns 1 if the budget is too small for even a single position.

        Issue #1964.

        Args:
            vram_budget_gb: Available VRAM in gigabytes.
            config: Cache configuration (max_seq_len field is ignored; the
                returned value replaces it).

        Returns:
            Maximum number of sequence positions that fit within the budget.
        """
        budget_bytes = int(vram_budget_gb * 1024 * 1024 * 1024)
        return _max_seq_from_budget(
            budget_bytes=budget_bytes,
            num_layers=config.num_layers,
            batch_size=config.batch_size,
            num_heads=config.num_heads,
            head_dim=config.head_dim,
            dtype_bytes=config.dtype_bytes,
        )

    def rtx4070_max_sequence_length(self, config: KVCacheConfig) -> int:
        """Max sequence length for an RTX 4070 using the recommended KV cache fraction.

        Issue #1964.

        Args:
            config: Cache configuration (max_seq_len is ignored).

        Returns:
            Max sequence positions fitting within RTX_4070_KV_CACHE_FRACTION
            of RTX_4070_VRAM_BYTES.
        """
        budget_bytes = int(RTX_4070_VRAM_BYTES * RTX_4070_KV_CACHE_FRACTION)
        return _max_seq_from_budget(
            budget_bytes=budget_bytes,
            num_layers=config.num_layers,
            batch_size=config.batch_size,
            num_heads=config.num_heads,
            head_dim=config.head_dim,
            dtype_bytes=config.dtype_bytes,
        )


# ---------------------------------------------------------------------------
# Module-level utility functions
# ---------------------------------------------------------------------------


def _compute_cache_bytes(
    *,
    num_layers: int,
    batch_size: int,
    max_seq_len: int,
    num_heads: int,
    head_dim: int,
    dtype_bytes: int,
) -> int:
    """Compute total bytes for fully-populated k and v caches.

    Issue #1964: Extracted helper so both manager methods share the formula.
    """
    # 2 tensors (k and v) per layer
    return 2 * num_layers * batch_size * max_seq_len * num_heads * head_dim * dtype_bytes


def _max_seq_from_budget(
    *,
    budget_bytes: int,
    num_layers: int,
    batch_size: int,
    num_heads: int,
    head_dim: int,
    dtype_bytes: int,
) -> int:
    """Solve for max_seq_len given a byte budget.

    Issue #1964.
    """
    # bytes_per_position = 2 * num_layers * batch_size * num_heads * head_dim * dtype_bytes
    bytes_per_position = 2 * num_layers * batch_size * num_heads * head_dim * dtype_bytes
    if bytes_per_position == 0:
        return 0
    return max(1, budget_bytes // bytes_per_position)


def _tensor_bytes(tensor: "torch.Tensor") -> int:
    """Return the total allocated bytes of a tensor (elements * element_size)."""
    return tensor.numel() * tensor.element_size()


__all__ = [
    "KVCacheConfig",
    "KVCacheManager",
    "LayerKVCache",
    "RTX_4070_KV_CACHE_FRACTION",
    "RTX_4070_VRAM_BYTES",
]
