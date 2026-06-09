# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for meta-device eviction utilities.

Covers: standard eviction, quantized per-param eviction, memory cleanup,
manager tracking, double-eviction guard, no-GPU fallback, missing-library
error paths.

Issue #1952: Meta device eviction for processed layers.
"""

from unittest.mock import MagicMock, patch

import pytest

from llm_shared.optimization.meta_eviction import (
    EvictionStats,
    MetaDeviceEvictionManager,
    clean_memory,
    evict_layer_to_meta,
    get_gpu_memory_allocated,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_torch_mock(cuda_available: bool = True, allocated: int = 1024) -> MagicMock:
    """Build a minimal torch mock with configurable CUDA state.

    Args:
        cuda_available: Value returned by ``torch.cuda.is_available()``.
        allocated: Value returned by ``torch.cuda.memory_allocated()``.

    Returns:
        MagicMock that mimics the torch module surface used by meta_eviction.
    """
    mock = MagicMock(name="torch")
    mock.cuda.is_available.return_value = cuda_available
    mock.cuda.memory_allocated.return_value = allocated
    mock.cuda.empty_cache.return_value = None
    return mock


def _make_layer_mock(param_names=("weight", "bias"), buffer_names=()) -> MagicMock:
    """Build a minimal nn.Module-like mock.

    Args:
        param_names: Iterable of parameter names to expose via named_parameters.
        buffer_names: Iterable of buffer names to expose via named_buffers.

    Returns:
        MagicMock with ``to``, ``named_parameters``, and ``named_buffers``
        configured.
    """
    layer = MagicMock(name="Layer")
    layer.__class__.__name__ = "FakeLinear"
    layer.named_parameters.return_value = [(n, MagicMock()) for n in param_names]
    layer.named_buffers.return_value = [(n, MagicMock()) for n in buffer_names]
    return layer


# ---------------------------------------------------------------------------
# TestCleanMemory
# ---------------------------------------------------------------------------


class TestCleanMemory:
    """Tests for clean_memory()."""

    def test_calls_empty_cache_when_cuda_available(self):
        """clean_memory calls torch.cuda.empty_cache when CUDA is present."""
        mock_torch = _make_torch_mock(cuda_available=True)
        with (
            patch(
                "llm_shared.optimization.meta_eviction._import_torch",
                return_value=mock_torch,
            ),
            patch("gc.collect", return_value=0),
        ):
            clean_memory()
        mock_torch.cuda.empty_cache.assert_called_once()

    def test_skips_empty_cache_when_cuda_unavailable(self):
        """clean_memory does not call empty_cache when CUDA is absent."""
        mock_torch = _make_torch_mock(cuda_available=False)
        with (
            patch(
                "llm_shared.optimization.meta_eviction._import_torch",
                return_value=mock_torch,
            ),
            patch("gc.collect", return_value=0),
        ):
            clean_memory()
        mock_torch.cuda.empty_cache.assert_not_called()

    def test_always_calls_gc_collect(self):
        """clean_memory always calls gc.collect regardless of CUDA state."""
        mock_torch = _make_torch_mock(cuda_available=False)
        with (
            patch(
                "llm_shared.optimization.meta_eviction._import_torch",
                return_value=mock_torch,
            ),
            patch("gc.collect", return_value=5) as mock_gc,
        ):
            clean_memory()
        mock_gc.assert_called_once()

    def test_no_gpu_fallback_still_calls_gc(self):
        """clean_memory degrades gracefully when torch is absent."""
        with (
            patch(
                "llm_shared.optimization.meta_eviction._import_torch",
                side_effect=RuntimeError("torch missing"),
            ),
            patch("gc.collect", return_value=0) as mock_gc,
        ):
            clean_memory()
        mock_gc.assert_called_once()


# ---------------------------------------------------------------------------
# TestGetGpuMemoryAllocated
# ---------------------------------------------------------------------------


class TestGetGpuMemoryAllocated:
    """Tests for get_gpu_memory_allocated()."""

    def test_returns_allocated_bytes_when_cuda_available(self):
        """Returns memory_allocated() value when CUDA is present."""
        mock_torch = _make_torch_mock(cuda_available=True, allocated=4096)
        with patch(
            "llm_shared.optimization.meta_eviction._import_torch",
            return_value=mock_torch,
        ):
            result = get_gpu_memory_allocated()
        assert result == 4096

    def test_returns_zero_when_cuda_unavailable(self):
        """Returns 0 when CUDA is absent."""
        mock_torch = _make_torch_mock(cuda_available=False)
        with patch(
            "llm_shared.optimization.meta_eviction._import_torch",
            return_value=mock_torch,
        ):
            result = get_gpu_memory_allocated()
        assert result == 0

    def test_returns_zero_when_torch_missing(self):
        """Returns 0 when PyTorch is not installed."""
        with patch(
            "llm_shared.optimization.meta_eviction._import_torch",
            side_effect=RuntimeError("torch missing"),
        ):
            result = get_gpu_memory_allocated()
        assert result == 0


# ---------------------------------------------------------------------------
# TestEvictLayerToMeta — standard path
# ---------------------------------------------------------------------------


class TestEvictLayerToMetaStandard:
    """Tests for evict_layer_to_meta() without a quantizer (standard path)."""

    def test_calls_layer_to_meta(self):
        """Standard eviction calls layer.to('meta')."""
        layer = _make_layer_mock()
        mock_torch = _make_torch_mock()
        with patch(
            "llm_shared.optimization.meta_eviction._import_torch",
            return_value=mock_torch,
        ):
            evict_layer_to_meta(layer)
        layer.to.assert_called_once_with("meta")

    def test_no_quantizer_does_not_import_accelerate(self):
        """Standard path does not import accelerate."""
        layer = _make_layer_mock()
        mock_torch = _make_torch_mock()
        with (
            patch(
                "llm_shared.optimization.meta_eviction._import_torch",
                return_value=mock_torch,
            ),
            patch("llm_shared.optimization.meta_eviction._import_accelerate") as mock_acc,
        ):
            evict_layer_to_meta(layer)
        mock_acc.assert_not_called()

    def test_raises_runtime_error_when_torch_missing(self):
        """Standard eviction raises RuntimeError when PyTorch absent."""
        layer = _make_layer_mock()
        with patch(
            "llm_shared.optimization.meta_eviction._import_torch",
            side_effect=RuntimeError("torch missing"),
        ):
            with pytest.raises(RuntimeError, match="torch missing"):
                evict_layer_to_meta(layer)


# ---------------------------------------------------------------------------
# TestEvictLayerToMeta — quantized per-param path
# ---------------------------------------------------------------------------


class TestEvictLayerToMetaQuantized:
    """Tests for evict_layer_to_meta() with quantizer (per-param path)."""

    def _run_quantized_eviction(self, layer, param_names=("weight", "bias"), buffer_names=()):
        """Helper: run quantized eviction with mocked torch + accelerate."""
        layer.named_parameters.return_value = [(n, MagicMock()) for n in param_names]
        layer.named_buffers.return_value = [(n, MagicMock()) for n in buffer_names]

        mock_torch = _make_torch_mock()
        mock_acc = MagicMock(name="accelerate")
        mock_set_fn = MagicMock(name="set_module_tensor_to_device")
        mock_acc.utils.set_module_tensor_to_device = mock_set_fn
        quantizer_stub = MagicMock(name="quantizer")

        with (
            patch(
                "llm_shared.optimization.meta_eviction._import_torch",
                return_value=mock_torch,
            ),
            patch(
                "llm_shared.optimization.meta_eviction._import_accelerate",
                return_value=mock_acc,
            ),
        ):
            evict_layer_to_meta(layer, quantizer=quantizer_stub)

        return mock_set_fn

    def test_calls_set_module_tensor_for_each_param(self):
        """Quantized path calls set_module_tensor_to_device for each parameter."""
        layer = MagicMock(name="Layer")
        set_fn = self._run_quantized_eviction(layer, param_names=("weight", "bias"))
        assert set_fn.call_count == 2
        # device is passed as keyword arg: set_fn(layer, name, device="meta")
        devices = [c.kwargs.get("device") for c in set_fn.call_args_list]
        assert all(d == "meta" for d in devices), "All tensors must target 'meta'"

    def test_calls_set_module_tensor_for_buffers(self):
        """Quantized path also handles named buffers."""
        layer = MagicMock(name="Layer")
        set_fn = self._run_quantized_eviction(layer, param_names=("weight",), buffer_names=("running_mean",))
        assert set_fn.call_count == 2  # 1 param + 1 buffer

    def test_does_not_call_layer_to(self):
        """Quantized path must NOT call layer.to() (avoids quantizer interference)."""
        layer = _make_layer_mock(param_names=("weight",))
        mock_torch = _make_torch_mock()
        mock_acc = MagicMock(name="accelerate")
        mock_acc.utils.set_module_tensor_to_device = MagicMock()
        quantizer_stub = MagicMock()

        with (
            patch(
                "llm_shared.optimization.meta_eviction._import_torch",
                return_value=mock_torch,
            ),
            patch(
                "llm_shared.optimization.meta_eviction._import_accelerate",
                return_value=mock_acc,
            ),
        ):
            evict_layer_to_meta(layer, quantizer=quantizer_stub)

        layer.to.assert_not_called()

    def test_raises_import_error_when_accelerate_missing(self):
        """Quantized path raises ImportError when accelerate is absent."""
        layer = _make_layer_mock()
        mock_torch = _make_torch_mock()
        quantizer_stub = MagicMock()

        with (
            patch(
                "llm_shared.optimization.meta_eviction._import_torch",
                return_value=mock_torch,
            ),
            patch(
                "llm_shared.optimization.meta_eviction._import_accelerate",
                side_effect=ImportError("accelerate not installed"),
            ),
        ):
            with pytest.raises(ImportError, match="accelerate"):
                evict_layer_to_meta(layer, quantizer=quantizer_stub)


# ---------------------------------------------------------------------------
# TestMetaDeviceEvictionManager
# ---------------------------------------------------------------------------


class TestMetaDeviceEvictionManager:
    """Tests for MetaDeviceEvictionManager."""

    # ------------------------------------------------------------------
    # is_evicted
    # ------------------------------------------------------------------

    def test_is_evicted_false_before_any_eviction(self):
        """Newly created manager reports no layers as evicted."""
        manager = MetaDeviceEvictionManager()
        assert manager.is_evicted(0) is False
        assert manager.is_evicted(5) is False

    def test_is_evicted_true_after_eviction(self):
        """is_evicted returns True after the layer has been evicted."""
        manager = MetaDeviceEvictionManager()
        layer = _make_layer_mock()
        mock_torch = _make_torch_mock(allocated=0)

        with (
            patch(
                "llm_shared.optimization.meta_eviction._import_torch",
                return_value=mock_torch,
            ),
            patch("llm_shared.optimization.meta_eviction.evict_layer_to_meta"),
            patch(
                "llm_shared.optimization.meta_eviction.get_gpu_memory_allocated",
                return_value=0,
            ),
        ):
            manager.evict(3, layer)

        assert manager.is_evicted(3) is True
        assert manager.is_evicted(0) is False

    # ------------------------------------------------------------------
    # evict — normal path
    # ------------------------------------------------------------------

    def test_evict_calls_evict_layer_to_meta(self):
        """evict() delegates to evict_layer_to_meta with correct args."""
        manager = MetaDeviceEvictionManager()
        layer = _make_layer_mock()

        with (
            patch("llm_shared.optimization.meta_eviction.evict_layer_to_meta") as mock_evict,
            patch(
                "llm_shared.optimization.meta_eviction.get_gpu_memory_allocated",
                return_value=0,
            ),
        ):
            result = manager.evict(1, layer)

        mock_evict.assert_called_once_with(layer, model=None, quantizer=None)
        assert result is True

    def test_evict_returns_false_for_already_evicted_layer(self):
        """evict() is a no-op and returns False for already-evicted layers."""
        manager = MetaDeviceEvictionManager()
        layer = _make_layer_mock()

        with (
            patch("llm_shared.optimization.meta_eviction.evict_layer_to_meta") as mock_evict,
            patch(
                "llm_shared.optimization.meta_eviction.get_gpu_memory_allocated",
                return_value=0,
            ),
        ):
            manager.evict(2, layer)
            result = manager.evict(2, layer)  # duplicate call

        # evict_layer_to_meta must only have been called once
        assert mock_evict.call_count == 1
        assert result is False

    def test_evict_increments_stats(self):
        """evict() increments evicted_count in stats."""
        manager = MetaDeviceEvictionManager()

        with (
            patch("llm_shared.optimization.meta_eviction.evict_layer_to_meta"),
            patch(
                "llm_shared.optimization.meta_eviction.get_gpu_memory_allocated",
                return_value=0,
            ),
        ):
            manager.evict(0, _make_layer_mock())
            manager.evict(1, _make_layer_mock())

        assert manager.stats.evicted_count == 2

    def test_evict_tracks_freed_bytes(self):
        """evict() accumulates freed GPU bytes in stats."""
        manager = MetaDeviceEvictionManager()
        allocated_sequence = [8192, 4096]  # before, after first eviction
        call_counter = {"n": 0}

        def _allocated():
            idx = call_counter["n"]
            call_counter["n"] += 1
            return allocated_sequence[idx] if idx < len(allocated_sequence) else 0

        with (
            patch("llm_shared.optimization.meta_eviction.evict_layer_to_meta"),
            patch(
                "llm_shared.optimization.meta_eviction.get_gpu_memory_allocated",
                side_effect=_allocated,
            ),
        ):
            manager.evict(0, _make_layer_mock())

        assert manager.stats.total_freed_bytes == 4096

    # ------------------------------------------------------------------
    # evicted_indices
    # ------------------------------------------------------------------

    def test_evicted_indices_returns_snapshot(self):
        """evicted_indices returns a copy of the internal set."""
        manager = MetaDeviceEvictionManager()

        with (
            patch("llm_shared.optimization.meta_eviction.evict_layer_to_meta"),
            patch(
                "llm_shared.optimization.meta_eviction.get_gpu_memory_allocated",
                return_value=0,
            ),
        ):
            manager.evict(0, _make_layer_mock())
            manager.evict(2, _make_layer_mock())

        indices = manager.evicted_indices()
        assert indices == {0, 2}

        # Mutating the returned set must not affect the manager
        indices.add(99)
        assert 99 not in manager.evicted_indices()

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    def test_reset_clears_evicted_set(self):
        """reset() removes all recorded eviction indices."""
        manager = MetaDeviceEvictionManager()

        with (
            patch("llm_shared.optimization.meta_eviction.evict_layer_to_meta"),
            patch(
                "llm_shared.optimization.meta_eviction.get_gpu_memory_allocated",
                return_value=0,
            ),
        ):
            manager.evict(0, _make_layer_mock())

        manager.reset()
        assert manager.is_evicted(0) is False
        assert manager.stats.evicted_count == 0

    def test_reset_returns_previous_stats(self):
        """reset() returns the stats accumulated before the reset."""
        manager = MetaDeviceEvictionManager()

        with (
            patch("llm_shared.optimization.meta_eviction.evict_layer_to_meta"),
            patch(
                "llm_shared.optimization.meta_eviction.get_gpu_memory_allocated",
                return_value=0,
            ),
        ):
            manager.evict(0, _make_layer_mock())
            manager.evict(1, _make_layer_mock())

        prev = manager.reset()
        assert isinstance(prev, EvictionStats)
        assert prev.evicted_count == 2


# ---------------------------------------------------------------------------
# TestEvictionStats
# ---------------------------------------------------------------------------


class TestEvictionStats:
    """Tests for EvictionStats dataclass."""

    def test_total_freed_mb_calculation(self):
        """total_freed_mb returns bytes converted to megabytes."""
        stats = EvictionStats(total_freed_bytes=1024 * 1024)
        assert stats.total_freed_mb == pytest.approx(1.0)

    def test_default_zero_values(self):
        """Default EvictionStats has all-zero fields."""
        stats = EvictionStats()
        assert stats.evicted_count == 0
        assert stats.total_freed_bytes == 0
        assert stats.total_freed_mb == pytest.approx(0.0)
