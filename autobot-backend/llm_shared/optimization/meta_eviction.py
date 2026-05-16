# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Meta-device eviction for processed transformer layers.

After a layer has been used during forward-pass computation its weights are no
longer needed in GPU/CPU RAM.  Moving those weights to the PyTorch meta device
("meta") frees the underlying storage immediately without requiring a separate
``del`` + GC cycle.  This is especially useful in pipeline-parallel or
sequential layer-by-layer inference patterns.

Key public surface:
- ``evict_layer_to_meta(layer, model=None, quantizer=None)`` — evict one layer.
- ``clean_memory()`` — CUDA cache flush + GC collect.
- ``get_gpu_memory_allocated()`` — current GPU bytes allocated.
- ``MetaDeviceEvictionManager`` — tracks evicted layers by index.

All torch imports are lazy so the module loads cleanly when PyTorch is absent.

Issue #1952: Meta device eviction for processed layers.
"""

import gc
from dataclasses import dataclass
from typing import Any, Set

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lazy import helpers
# ---------------------------------------------------------------------------


def _import_torch() -> Any:
    """Lazily import torch; raises RuntimeError with guidance if absent."""
    try:
        import torch  # noqa: PLC0415

        return torch
    except (ImportError, RuntimeError) as exc:
        raise RuntimeError("PyTorch is required for meta-device eviction. " "Install with: pip install torch") from exc


def _import_accelerate() -> Any:
    """Lazily import accelerate; raises ImportError with guidance if absent."""
    try:
        import accelerate  # noqa: PLC0415

        return accelerate
    except (ImportError, RuntimeError) as exc:
        raise ImportError(
            "accelerate is required for per-parameter meta-device eviction. " "Install with: pip install accelerate"
        ) from exc


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def clean_memory() -> None:
    """Release GPU and CPU memory held by deallocated tensors.

    Calls ``torch.cuda.empty_cache()`` (when CUDA is available),
    ``gc.collect()`` to reclaim Python-managed objects, and
    ``malloc_trim(0)`` on Linux to return freed heap pages to the OS.

    Issue #1952, #3165.
    """
    try:
        torch = _import_torch()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.debug("torch.cuda.empty_cache() completed")
    except RuntimeError:
        logger.debug("PyTorch unavailable — skipping CUDA cache flush")

    collected = gc.collect()
    logger.debug("gc.collect() reclaimed %d objects", collected)

    # Issue #3165: return freed heap memory to the OS (Linux only).
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
        logger.debug("malloc_trim(0) completed")
    except Exception:  # noqa: BLE001
        pass


def get_gpu_memory_allocated() -> int:
    """Return the number of bytes currently allocated on the default CUDA device.

    Returns:
        Bytes allocated on the current CUDA device, or 0 when CUDA is
        unavailable.

    Issue #1952.
    """
    try:
        torch = _import_torch()
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated()
            logger.debug("GPU memory allocated: %d bytes", allocated)
            return int(allocated)
    except RuntimeError:
        pass

    logger.debug("CUDA unavailable — returning 0 for GPU memory allocated")
    return 0


def evict_layer_to_meta(
    layer: Any,
    model: Any | None = None,
    quantizer: Any | None = None,
) -> None:
    """Move a transformer layer's parameters to the PyTorch meta device.

    Evicting a layer to "meta" replaces its weight tensors with zero-storage
    placeholders, freeing both GPU VRAM and CPU RAM for that layer immediately.

    Two eviction strategies are supported:

    1. **Per-parameter via accelerate** (used when *quantizer* is provided):
       Calls ``accelerate.utils.set_module_tensor_to_device`` for each
       named parameter and buffer.  This path handles quantized modules
       (GPTQ, AWQ, BitsAndBytes) whose ``to()`` method is overridden or
       restricted by the quantization library.

    2. **Standard** (used when no *quantizer* is provided):
       Calls ``layer.to("meta")`` directly.  This is the simplest path and
       works for any standard ``nn.Module``.

    Args:
        layer: The ``nn.Module`` instance to evict.
        model: Unused; reserved for future layer-path resolution
            (e.g. looking up the module path within a parent model).
            Pass ``None`` to use the standard eviction path.
        quantizer: A :class:`~llm_shared.optimization.hf_quantizer.HfQuantizerWrapper`
            (or any object whose presence indicates a quantized model).
            When provided, the per-parameter accelerate path is used.

    Raises:
        RuntimeError: If PyTorch is not installed.
        ImportError: If *quantizer* is provided but ``accelerate`` is not
            installed.

    Issue #1952.
    """
    layer_repr = _layer_repr(layer)

    if quantizer is not None:
        _evict_quantized_layer(layer, layer_repr)
    else:
        _evict_standard_layer(layer, layer_repr)


# ---------------------------------------------------------------------------
# Private eviction helpers
# ---------------------------------------------------------------------------


def _layer_repr(layer: Any) -> str:
    """Return a short identifier string for logging.

    Args:
        layer: The module to describe.

    Returns:
        String like ``"Linear"`` or ``"<unknown>"`` for log messages.
    """
    try:
        return type(layer).__name__
    except Exception:
        return "<unknown>"


def _evict_standard_layer(layer: Any, layer_repr: str) -> None:
    """Evict using the standard ``nn.Module.to('meta')`` path.

    Args:
        layer: The ``nn.Module`` to evict.
        layer_repr: Short description string for log messages.
    """
    torch = _import_torch()
    before = _cuda_allocated_safe(torch)
    layer.to("meta")
    after = _cuda_allocated_safe(torch)
    freed = max(0, before - after)
    logger.info(
        "Evicted layer %s to meta device (freed ~%d bytes from CUDA)",
        layer_repr,
        freed,
    )


def _evict_quantized_layer(layer: Any, layer_repr: str) -> None:
    """Evict each parameter and buffer individually via accelerate.

    ``set_module_tensor_to_device`` understands quantization-aware modules
    and relocates tensors correctly without triggering quantizer callbacks
    that would fire on a plain ``layer.to(device)`` call.

    Args:
        layer: The ``nn.Module`` to evict.
        layer_repr: Short description string for log messages.
    """
    _import_torch()  # ensure torch is present before importing accelerate
    accelerate = _import_accelerate()
    set_fn = accelerate.utils.set_module_tensor_to_device

    torch = _import_torch()
    before = _cuda_allocated_safe(torch)

    param_names = [name for name, _ in layer.named_parameters()] + [name for name, _ in layer.named_buffers()]

    for name in param_names:
        set_fn(layer, name, device="meta")

    after = _cuda_allocated_safe(torch)
    freed = max(0, before - after)
    logger.info(
        "Evicted quantized layer %s to meta device via per-param path " "(%d tensors, freed ~%d bytes from CUDA)",
        layer_repr,
        len(param_names),
        freed,
    )


def _cuda_allocated_safe(torch: Any) -> int:
    """Return CUDA bytes allocated, or 0 if CUDA is unavailable.

    Args:
        torch: The already-imported torch module.

    Returns:
        Allocated bytes as an integer.
    """
    try:
        if torch.cuda.is_available():
            return int(torch.cuda.memory_allocated())
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# MetaDeviceEvictionManager
# ---------------------------------------------------------------------------


@dataclass
class EvictionStats:
    """Statistics accumulated by :class:`MetaDeviceEvictionManager`.

    Attributes:
        evicted_count: Total number of layers evicted this session.
        total_freed_bytes: Cumulative GPU bytes freed across all evictions.
    """

    evicted_count: int = 0
    total_freed_bytes: int = 0

    @property
    def total_freed_mb(self) -> float:
        """Total GPU memory freed in megabytes."""
        return self.total_freed_bytes / (1024 * 1024)


class MetaDeviceEvictionManager:
    """Track and manage per-layer meta-device eviction.

    Maintains a set of already-evicted layer indices so callers can avoid
    double-eviction.  Each call to :meth:`evict` records the layer index
    and delegates to :func:`evict_layer_to_meta`.

    Typical usage in a pipeline-parallel loop::

        manager = MetaDeviceEvictionManager()
        for idx, layer in enumerate(model.layers):
            output = layer(hidden_states)
            manager.evict(idx, layer)
            clean_memory()

    Issue #1952.
    """

    def __init__(self) -> None:
        """Initialise with an empty evicted-index set."""
        self._evicted: Set[int] = set()
        self._stats: EvictionStats = EvictionStats()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def stats(self) -> EvictionStats:
        """Cumulative eviction statistics (read-only view)."""
        return self._stats

    def is_evicted(self, layer_idx: int) -> bool:
        """Return True if *layer_idx* has already been evicted.

        Args:
            layer_idx: Zero-based index identifying the layer.

        Returns:
            True when the layer has been moved to the meta device by this
            manager instance.
        """
        return layer_idx in self._evicted

    def evict(
        self,
        layer_idx: int,
        layer: Any,
        model: Any | None = None,
        quantizer: Any | None = None,
    ) -> bool:
        """Evict *layer* to the meta device and record the index.

        If *layer_idx* was already evicted this call is a no-op (returns
        ``False``).

        Args:
            layer_idx: Zero-based index identifying the layer.
            layer: The ``nn.Module`` instance to evict.
            model: Forwarded to :func:`evict_layer_to_meta` (reserved).
            quantizer: Forwarded to :func:`evict_layer_to_meta`.  When
                provided, the per-parameter accelerate path is used.

        Returns:
            True when the eviction was performed, False when it was skipped
            because the layer was already evicted.
        """
        if layer_idx in self._evicted:
            logger.debug("Layer %d already evicted — skipping", layer_idx)
            return False

        before = get_gpu_memory_allocated()
        evict_layer_to_meta(layer, model=model, quantizer=quantizer)
        after = get_gpu_memory_allocated()

        freed = max(0, before - after)
        self._evicted.add(layer_idx)
        self._stats.evicted_count += 1
        self._stats.total_freed_bytes += freed

        logger.info(
            "MetaDeviceEvictionManager: evicted layer %d (freed ~%d bytes, " "total evicted=%d)",
            layer_idx,
            freed,
            self._stats.evicted_count,
        )
        return True

    def reset(self) -> EvictionStats:
        """Reset the eviction record and return the previous statistics.

        Returns:
            The :class:`EvictionStats` accumulated before the reset.
        """
        previous = EvictionStats(
            evicted_count=self._stats.evicted_count,
            total_freed_bytes=self._stats.total_freed_bytes,
        )
        self._evicted = set()
        self._stats = EvictionStats()
        logger.debug("MetaDeviceEvictionManager reset")
        return previous

    def evicted_indices(self) -> Set[int]:
        """Return a snapshot of all evicted layer indices.

        Returns:
            A copy of the internal evicted-index set.
        """
        return set(self._evicted)


__all__ = [
    "clean_memory",
    "evict_layer_to_meta",
    "get_gpu_memory_allocated",
    "EvictionStats",
    "MetaDeviceEvictionManager",
]
