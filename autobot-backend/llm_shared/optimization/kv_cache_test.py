# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for layer-aligned KV cache management.

Issue #1964: Layer-aligned KV cache management for sequential layer processing.
"""

import types

import pytest
import torch

# Detect conftest MagicMock torch stub; skip tensor-operation tests when absent (#5728)
_TORCH_IS_STUB = not isinstance(torch, types.ModuleType)
requires_torch = pytest.mark.skipif(_TORCH_IS_STUB, reason="requires real PyTorch")

from llm_shared.optimization.kv_cache import (
    RTX_4070_KV_CACHE_FRACTION,
    RTX_4070_VRAM_BYTES,
    KVCacheConfig,
    KVCacheManager,
    LayerKVCache,
    _compute_cache_bytes,
    _max_seq_from_budget,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    num_layers: int = 4,
    num_heads: int = 8,
    head_dim: int = 64,
    max_seq_len: int = 512,
    dtype: str = "fp16",
    device: str = "cpu",
    batch_size: int = 1,
) -> KVCacheConfig:
    """Create a test KVCacheConfig with sensible defaults."""
    return KVCacheConfig(
        num_layers=num_layers,
        num_heads=num_heads,
        head_dim=head_dim,
        max_seq_len=max_seq_len,
        dtype=dtype,
        device=device,
        batch_size=batch_size,
    )


def _make_kv(
    batch: int = 1,
    seq: int = 4,
    heads: int = 8,
    head_dim: int = 64,
    dtype=torch.float16,
) -> tuple:
    """Return (k, v) tensors shaped [batch, seq, heads, head_dim]."""
    k = torch.randn(batch, seq, heads, head_dim, dtype=dtype)
    v = torch.randn(batch, seq, heads, head_dim, dtype=dtype)
    return k, v


# ---------------------------------------------------------------------------
# KVCacheConfig tests
# ---------------------------------------------------------------------------


class TestKVCacheConfig:
    """Tests for KVCacheConfig dataclass and validation."""

    def test_default_dtype_is_fp16(self):
        """Default dtype should be 'fp16'."""
        cfg = _make_config()
        assert cfg.dtype == "fp16"

    def test_dtype_bytes_fp16(self):
        """fp16 should report 2 bytes per element."""
        cfg = _make_config(dtype="fp16")
        assert cfg.dtype_bytes == 2

    def test_dtype_bytes_fp32(self):
        """fp32 should report 4 bytes per element."""
        cfg = _make_config(dtype="fp32")
        assert cfg.dtype_bytes == 4

    def test_dtype_bytes_bf16(self):
        """bf16 should report 2 bytes per element."""
        cfg = _make_config(dtype="bf16")
        assert cfg.dtype_bytes == 2

    def test_dtype_aliases(self):
        """float16 / bfloat16 / float32 aliases should be accepted."""
        for alias, expected_bytes in (("float16", 2), ("bfloat16", 2), ("float32", 4)):
            cfg = _make_config(dtype=alias)
            assert cfg.dtype_bytes == expected_bytes

    def test_invalid_dtype_raises(self):
        """Unknown dtype string should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported dtype"):
            _make_config(dtype="int8")

    def test_zero_num_layers_raises(self):
        """num_layers=0 should raise ValueError."""
        with pytest.raises(ValueError, match="num_layers"):
            _make_config(num_layers=0)

    def test_zero_num_heads_raises(self):
        """num_heads=0 should raise ValueError."""
        with pytest.raises(ValueError, match="num_heads"):
            _make_config(num_heads=0)

    def test_zero_head_dim_raises(self):
        """head_dim=0 should raise ValueError."""
        with pytest.raises(ValueError, match="head_dim"):
            _make_config(head_dim=0)

    def test_zero_max_seq_len_raises(self):
        """max_seq_len=0 should raise ValueError."""
        with pytest.raises(ValueError, match="max_seq_len"):
            _make_config(max_seq_len=0)

    def test_zero_batch_size_raises(self):
        """batch_size=0 should raise ValueError."""
        with pytest.raises(ValueError, match="batch_size"):
            _make_config(batch_size=0)

    def test_valid_config_creates_successfully(self):
        """A fully valid config should construct without error."""
        cfg = KVCacheConfig(
            num_layers=32,
            num_heads=32,
            head_dim=128,
            max_seq_len=4096,
            dtype="fp16",
            device="cpu",
            batch_size=2,
        )
        assert cfg.num_layers == 32
        assert cfg.batch_size == 2


# ---------------------------------------------------------------------------
# LayerKVCache — basic get / update
# ---------------------------------------------------------------------------


@requires_torch
class TestLayerKVCacheGetUpdate:
    """Tests for LayerKVCache.get() and update()."""

    def test_get_uninitialized_layer_returns_none(self):
        """get() on a layer that has never been updated should return None."""
        cache = LayerKVCache(_make_config())
        assert cache.get(0) is None

    def test_update_and_get_single_layer(self):
        """Updating one layer should make its data retrievable via get()."""
        cfg = _make_config(num_heads=4, head_dim=32, max_seq_len=64)
        cache = LayerKVCache(cfg)
        k, v = _make_kv(seq=8, heads=4, head_dim=32)
        ret_k, ret_v = cache.update(0, k, v)

        assert ret_k.shape == (1, 8, 4, 32)
        assert ret_v.shape == (1, 8, 4, 32)
        assert torch.allclose(ret_k, k)
        assert torch.allclose(ret_v, v)

    def test_get_returns_only_filled_portion(self):
        """get() should not expose unfilled (zero-padded) positions."""
        cfg = _make_config(num_heads=4, head_dim=16, max_seq_len=128)
        cache = LayerKVCache(cfg)
        k, v = _make_kv(seq=5, heads=4, head_dim=16)
        cache.update(0, k, v)

        result = cache.get(0)
        assert result is not None
        gk, gv = result
        assert gk.shape[1] == 5
        assert gv.shape[1] == 5

    def test_update_accumulates_across_steps(self):
        """Multiple updates to the same layer should accumulate positions."""
        cfg = _make_config(num_heads=4, head_dim=16, max_seq_len=64)
        cache = LayerKVCache(cfg)
        k1, v1 = _make_kv(seq=4, heads=4, head_dim=16)
        k2, v2 = _make_kv(seq=6, heads=4, head_dim=16)

        cache.update(0, k1, v1)
        ret_k, ret_v = cache.update(0, k2, v2)

        assert ret_k.shape[1] == 10
        assert ret_v.shape[1] == 10
        # First slice must equal k1
        assert torch.allclose(ret_k[:, :4, :, :], k1)
        assert torch.allclose(ret_k[:, 4:, :, :], k2)

    def test_update_independent_layers(self):
        """Updating different layers should not interfere with each other."""
        cfg = _make_config(num_layers=4, num_heads=4, head_dim=16, max_seq_len=64)
        cache = LayerKVCache(cfg)
        k0, v0 = _make_kv(seq=3, heads=4, head_dim=16)
        k2, v2 = _make_kv(seq=7, heads=4, head_dim=16)

        cache.update(0, k0, v0)
        cache.update(2, k2, v2)

        r0 = cache.get(0)
        r1 = cache.get(1)
        r2 = cache.get(2)

        assert r0 is not None and r0[0].shape[1] == 3
        assert r1 is None
        assert r2 is not None and r2[0].shape[1] == 7

    def test_overflow_raises_value_error(self):
        """Writing beyond max_seq_len should raise ValueError."""
        cfg = _make_config(num_heads=2, head_dim=8, max_seq_len=10)
        cache = LayerKVCache(cfg)
        k, v = _make_kv(seq=11, heads=2, head_dim=8)
        with pytest.raises(ValueError, match="KV cache overflow"):
            cache.update(0, k, v)

    def test_exact_fill_to_max_seq_len(self):
        """Writing exactly max_seq_len positions should succeed."""
        cfg = _make_config(num_heads=2, head_dim=8, max_seq_len=16)
        cache = LayerKVCache(cfg)
        k, v = _make_kv(seq=16, heads=2, head_dim=8)
        ret_k, ret_v = cache.update(0, k, v)
        assert ret_k.shape[1] == 16


# ---------------------------------------------------------------------------
# LayerKVCache — shape validation
# ---------------------------------------------------------------------------


@requires_torch
class TestLayerKVCacheValidation:
    """Tests for input tensor shape validation."""

    def test_wrong_batch_size_raises(self):
        """Batch size mismatch should raise ValueError."""
        cfg = _make_config(batch_size=1, num_heads=4, head_dim=16)
        cache = LayerKVCache(cfg)
        k = torch.randn(2, 4, 4, 16)  # batch=2, but config says 1
        v = torch.randn(2, 4, 4, 16)
        with pytest.raises(ValueError, match="batch size"):
            cache.update(0, k, v)

    def test_wrong_num_heads_raises(self):
        """num_heads mismatch should raise ValueError."""
        cfg = _make_config(num_heads=4, head_dim=16)
        cache = LayerKVCache(cfg)
        k = torch.randn(1, 4, 8, 16)  # heads=8, but config says 4
        v = torch.randn(1, 4, 8, 16)
        with pytest.raises(ValueError, match="num_heads"):
            cache.update(0, k, v)

    def test_wrong_head_dim_raises(self):
        """head_dim mismatch should raise ValueError."""
        cfg = _make_config(num_heads=4, head_dim=16)
        cache = LayerKVCache(cfg)
        k = torch.randn(1, 4, 4, 32)  # head_dim=32, but config says 16
        v = torch.randn(1, 4, 4, 32)
        with pytest.raises(ValueError, match="head_dim"):
            cache.update(0, k, v)

    def test_wrong_tensor_rank_raises(self):
        """Non-4D tensors should raise ValueError."""
        cfg = _make_config(num_heads=4, head_dim=16)
        cache = LayerKVCache(cfg)
        k = torch.randn(1, 4, 16)  # 3D, not 4D
        v = torch.randn(1, 4, 16)
        with pytest.raises(ValueError, match="4D"):
            cache.update(0, k, v)


# ---------------------------------------------------------------------------
# LayerKVCache — trim_to_length
# ---------------------------------------------------------------------------


@requires_torch
class TestLayerKVCacheTrim:
    """Tests for LayerKVCache.trim_to_length()."""

    def test_trim_reduces_filled_len(self):
        """trim_to_length should reduce filled_len for all populated layers."""
        cfg = _make_config(num_heads=2, head_dim=8, max_seq_len=64)
        cache = LayerKVCache(cfg)
        k, v = _make_kv(seq=20, heads=2, head_dim=8)
        cache.update(0, k, v)
        cache.update(1, k, v)

        cache.trim_to_length(10)

        r0 = cache.get(0)
        r1 = cache.get(1)
        assert r0 is not None and r0[0].shape[1] == 10
        assert r1 is not None and r1[0].shape[1] == 10

    def test_trim_to_zero_clears_visible_data(self):
        """trim_to_length(0) should make get() return None for all layers."""
        cfg = _make_config(num_heads=2, head_dim=8, max_seq_len=32)
        cache = LayerKVCache(cfg)
        k, v = _make_kv(seq=5, heads=2, head_dim=8)
        cache.update(0, k, v)

        cache.trim_to_length(0)

        assert cache.get(0) is None

    def test_trim_larger_than_filled_is_no_op(self):
        """trim_to_length >= filled_len should not change anything."""
        cfg = _make_config(num_heads=2, head_dim=8, max_seq_len=64)
        cache = LayerKVCache(cfg)
        k, v = _make_kv(seq=5, heads=2, head_dim=8)
        cache.update(0, k, v)

        cache.trim_to_length(100)

        r = cache.get(0)
        assert r is not None and r[0].shape[1] == 5

    def test_trim_negative_raises(self):
        """trim_to_length with a negative value should raise ValueError."""
        cfg = _make_config()
        cache = LayerKVCache(cfg)
        with pytest.raises(ValueError, match="max_len"):
            cache.trim_to_length(-1)

    def test_trim_preserves_content_up_to_limit(self):
        """After trim, the remaining content should match the original."""
        cfg = _make_config(num_heads=2, head_dim=8, max_seq_len=64)
        cache = LayerKVCache(cfg)
        k, v = _make_kv(seq=12, heads=2, head_dim=8)
        cache.update(0, k, v)

        cache.trim_to_length(6)

        r = cache.get(0)
        assert r is not None
        assert torch.allclose(r[0], k[:, :6, :, :])
        assert torch.allclose(r[1], v[:, :6, :, :])


# ---------------------------------------------------------------------------
# LayerKVCache — clear and memory_usage_bytes
# ---------------------------------------------------------------------------


@requires_torch
class TestLayerKVCacheClearMemory:
    """Tests for clear() and memory_usage_bytes()."""

    def test_clear_resets_all_layers(self):
        """clear() should make all layers return None from get()."""
        cfg = _make_config(num_heads=2, head_dim=8, max_seq_len=32)
        cache = LayerKVCache(cfg)
        k, v = _make_kv(seq=4, heads=2, head_dim=8)
        for i in range(3):
            cache.update(i, k, v)

        cache.clear()

        for i in range(3):
            assert cache.get(i) is None
        assert cache.num_filled_layers == 0

    def test_memory_usage_zero_before_any_update(self):
        """memory_usage_bytes() should be 0 before any update."""
        cfg = _make_config()
        cache = LayerKVCache(cfg)
        assert cache.memory_usage_bytes() == 0

    def test_memory_usage_increases_after_update(self):
        """memory_usage_bytes() should grow after an update."""
        cfg = _make_config(num_heads=4, head_dim=32, max_seq_len=64)
        cache = LayerKVCache(cfg)
        k, v = _make_kv(seq=8, heads=4, head_dim=32)
        cache.update(0, k, v)
        assert cache.memory_usage_bytes() > 0

    def test_memory_usage_matches_formula(self):
        """memory_usage_bytes() should equal 2 * max_seq * heads * head_dim * dtype_bytes."""
        cfg = _make_config(num_heads=4, head_dim=32, max_seq_len=128, dtype="fp32")
        cache = LayerKVCache(cfg)
        k = torch.zeros(1, 10, 4, 32, dtype=torch.float32)
        v = torch.zeros(1, 10, 4, 32, dtype=torch.float32)
        cache.update(0, k, v)

        # One layer allocated: 2 tensors of shape (1, 128, 4, 32) at 4 bytes each
        expected = 2 * 1 * 128 * 4 * 32 * 4
        assert cache.memory_usage_bytes() == expected

    def test_memory_usage_zero_after_clear(self):
        """memory_usage_bytes() should return 0 after clear()."""
        cfg = _make_config(num_heads=2, head_dim=8, max_seq_len=16)
        cache = LayerKVCache(cfg)
        k, v = _make_kv(seq=4, heads=2, head_dim=8)
        cache.update(0, k, v)
        cache.clear()
        assert cache.memory_usage_bytes() == 0


# ---------------------------------------------------------------------------
# LayerKVCache — num_filled_layers
# ---------------------------------------------------------------------------


@requires_torch
class TestNumFilledLayers:
    """Tests for the num_filled_layers property."""

    def test_starts_at_zero(self):
        """New cache should have no filled layers."""
        assert LayerKVCache(_make_config()).num_filled_layers == 0

    def test_increases_per_layer(self):
        """num_filled_layers should count each layer independently."""
        cfg = _make_config(num_heads=2, head_dim=8)
        cache = LayerKVCache(cfg)
        k, v = _make_kv(seq=2, heads=2, head_dim=8)
        for expected, layer in enumerate((0, 2, 3), start=1):
            cache.update(layer, k, v)
            assert cache.num_filled_layers == expected


# ---------------------------------------------------------------------------
# KVCacheManager — memory estimation
# ---------------------------------------------------------------------------


class TestKVCacheManagerEstimateMemory:
    """Tests for KVCacheManager.estimate_memory()."""

    def test_estimate_formula_correctness(self):
        """Estimate should equal 2 * layers * batch * seq * heads * dim * dtype_bytes."""
        cfg = _make_config(
            num_layers=8,
            batch_size=2,
            max_seq_len=512,
            num_heads=8,
            head_dim=64,
            dtype="fp16",
        )
        manager = KVCacheManager()
        expected = 2 * 8 * 2 * 512 * 8 * 64 * 2
        assert manager.estimate_memory(cfg) == expected

    def test_fp32_uses_twice_fp16_memory(self):
        """fp32 config should use twice the memory of an identical fp16 config."""
        cfg_16 = _make_config(dtype="fp16")
        cfg_32 = _make_config(dtype="fp32")
        manager = KVCacheManager()
        assert manager.estimate_memory(cfg_32) == 2 * manager.estimate_memory(cfg_16)

    def test_doubling_layers_doubles_memory(self):
        """Doubling num_layers should double the estimate."""
        manager = KVCacheManager()
        base = _make_config(num_layers=4)
        double = _make_config(num_layers=8)
        assert manager.estimate_memory(double) == 2 * manager.estimate_memory(base)

    def test_doubling_seq_len_doubles_memory(self):
        """Doubling max_seq_len should double the estimate."""
        manager = KVCacheManager()
        base = _make_config(max_seq_len=256)
        double = _make_config(max_seq_len=512)
        assert manager.estimate_memory(double) == 2 * manager.estimate_memory(base)


# ---------------------------------------------------------------------------
# KVCacheManager — max_sequence_length
# ---------------------------------------------------------------------------


class TestKVCacheManagerMaxSeqLen:
    """Tests for KVCacheManager.max_sequence_length()."""

    def test_returns_positive_integer(self):
        """max_sequence_length should always return a positive integer."""
        manager = KVCacheManager()
        cfg = _make_config()
        result = manager.max_sequence_length(vram_budget_gb=1.0, config=cfg)
        assert isinstance(result, int)
        assert result >= 1

    def test_larger_budget_gives_longer_sequence(self):
        """Larger VRAM budget should allow longer sequences."""
        manager = KVCacheManager()
        cfg = _make_config()
        small = manager.max_sequence_length(vram_budget_gb=1.0, config=cfg)
        large = manager.max_sequence_length(vram_budget_gb=4.0, config=cfg)
        assert large > small

    def test_tiny_budget_returns_at_least_one(self):
        """Even a 1-byte budget should return at least 1 (no zero result)."""
        manager = KVCacheManager()
        # Use a very small budget expressed as a fraction of a GB
        result = manager.max_sequence_length(vram_budget_gb=1e-9, config=_make_config())
        assert result >= 1

    def test_result_consistent_with_estimate(self):
        """Estimate for the returned max_seq_len should not exceed the budget."""
        manager = KVCacheManager()
        vram_gb = 2.0
        base_cfg = _make_config(num_layers=12, num_heads=12, head_dim=64, dtype="fp16")
        max_seq = manager.max_sequence_length(vram_budget_gb=vram_gb, config=base_cfg)

        actual_cfg = KVCacheConfig(
            num_layers=base_cfg.num_layers,
            num_heads=base_cfg.num_heads,
            head_dim=base_cfg.head_dim,
            max_seq_len=max_seq,
            dtype=base_cfg.dtype,
            device=base_cfg.device,
            batch_size=base_cfg.batch_size,
        )
        budget_bytes = int(vram_gb * 1024 * 1024 * 1024)
        assert manager.estimate_memory(actual_cfg) <= budget_bytes

    def test_rtx4070_helper_returns_positive(self):
        """rtx4070_max_sequence_length should return a positive integer."""
        manager = KVCacheManager()
        # Llama-7B-like config
        cfg = _make_config(num_layers=32, num_heads=32, head_dim=128)
        result = manager.rtx4070_max_sequence_length(cfg)
        assert isinstance(result, int)
        assert result >= 1

    def test_rtx4070_helper_respects_fraction(self):
        """RTX 4070 result should be <= the fractional budget."""
        manager = KVCacheManager()
        cfg = _make_config(num_layers=32, num_heads=32, head_dim=128)
        result = manager.rtx4070_max_sequence_length(cfg)
        budget_bytes = int(RTX_4070_VRAM_BYTES * RTX_4070_KV_CACHE_FRACTION)

        actual_cfg = KVCacheConfig(
            num_layers=cfg.num_layers,
            num_heads=cfg.num_heads,
            head_dim=cfg.head_dim,
            max_seq_len=result,
            dtype=cfg.dtype,
            device=cfg.device,
            batch_size=cfg.batch_size,
        )
        assert manager.estimate_memory(actual_cfg) <= budget_bytes


# ---------------------------------------------------------------------------
# KVCacheManager — create_cache factory
# ---------------------------------------------------------------------------


class TestKVCacheManagerCreateCache:
    """Tests for KVCacheManager.create_cache()."""

    def test_returns_layer_kv_cache_instance(self):
        """create_cache() should return a LayerKVCache."""
        manager = KVCacheManager()
        cfg = _make_config()
        cache = manager.create_cache(cfg)
        assert isinstance(cache, LayerKVCache)

    def test_created_cache_config_matches(self):
        """The created cache should carry the exact config passed in."""
        manager = KVCacheManager()
        cfg = _make_config(num_layers=6, num_heads=6, head_dim=48, max_seq_len=256)
        cache = manager.create_cache(cfg)
        assert cache.config is cfg

    def test_created_cache_starts_empty(self):
        """A freshly created cache should have no filled layers."""
        manager = KVCacheManager()
        cache = manager.create_cache(_make_config())
        assert cache.num_filled_layers == 0
        assert cache.memory_usage_bytes() == 0


# ---------------------------------------------------------------------------
# Internal formula helpers
# ---------------------------------------------------------------------------


class TestInternalHelpers:
    """Tests for _compute_cache_bytes and _max_seq_from_budget."""

    def test_compute_cache_bytes_simple(self):
        """Manual computation: 2 * 2 * 1 * 4 * 2 * 8 * 2 = 512 bytes."""
        result = _compute_cache_bytes(
            num_layers=2,
            batch_size=1,
            max_seq_len=4,
            num_heads=2,
            head_dim=8,
            dtype_bytes=2,
        )
        assert result == 2 * 2 * 1 * 4 * 2 * 8 * 2

    def test_max_seq_from_budget_inverse_of_compute(self):
        """max_seq from budget should invert compute_cache_bytes."""
        kwargs = dict(num_layers=2, batch_size=1, num_heads=2, head_dim=8, dtype_bytes=2)
        seq = 100
        budget = _compute_cache_bytes(max_seq_len=seq, **kwargs)
        recovered = _max_seq_from_budget(budget_bytes=budget, **kwargs)
        assert recovered == seq

    def test_max_seq_from_zero_budget_returns_one(self):
        """Budget of 0 should return 1 (minimum one position)."""
        result = _max_seq_from_budget(
            budget_bytes=0,
            num_layers=1,
            batch_size=1,
            num_heads=1,
            head_dim=1,
            dtype_bytes=2,
        )
        assert result == 1
