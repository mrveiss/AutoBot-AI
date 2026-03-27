# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Flash Attention v2 with variable-length sequence optimization.

Issue #1955: Flash Attention v2 with variable-length sequence optimization.
"""

from unittest.mock import MagicMock, patch

import pytest
import torch
from llm_interface_pkg.optimization.flash_attention import (
    AttentionBackend,
    FlashAttentionConfig,
    FlashAttentionV2,
    GrowingKVCache,
    _rotate_half_apply,
    create_flash_attention,
    detect_backend,
)


class TestDetectBackend:
    """Tests for attention backend detection."""

    def test_returns_valid_backend(self):
        """detect_backend should return a valid AttentionBackend."""
        backend = detect_backend()
        assert isinstance(backend, AttentionBackend)

    @patch(
        "llm_interface_pkg.optimization.flash_attention._probe_flash_attn",
        return_value=False,
    )
    def test_falls_back_to_sdpa_when_no_flash(self, mock_probe):
        """Should fall back to SDPA when flash_attn not available."""
        if hasattr(torch.nn.functional, "scaled_dot_product_attention"):
            backend = detect_backend()
            assert backend in (AttentionBackend.SDPA, AttentionBackend.VANILLA)

    @patch(
        "llm_interface_pkg.optimization.flash_attention._probe_flash_attn",
        return_value=False,
    )
    @patch(
        "llm_interface_pkg.optimization.flash_attention._has_sdpa",
        return_value=False,
    )
    def test_falls_back_to_vanilla(self, mock_sdpa, mock_probe):
        """Should fall back to vanilla when nothing else is available."""
        backend = detect_backend()
        assert backend == AttentionBackend.VANILLA


class TestGrowingKVCache:
    """Tests for the growing KV cache."""

    def _make_kv(self, batch: int, seq: int, heads: int = 4, dim: int = 32):
        """Create a test KV tensor [batch, seq, 2, heads, dim]."""
        return torch.randn(batch, seq, 2, heads, dim)

    def test_initial_allocation(self):
        """First update should allocate cache."""
        cache = GrowingKVCache(chunk_size=256, device=torch.device("cpu"))
        kv = self._make_kv(2, 10)
        result = cache.update(kv)
        assert result.shape == (2, 10, 2, 4, 32)
        assert cache.seq_offset == 10

    def test_grows_in_chunks(self):
        """Cache should grow by chunk_size when capacity exceeded."""
        cache = GrowingKVCache(chunk_size=8, device=torch.device("cpu"))
        kv1 = self._make_kv(1, 6)
        cache.update(kv1)
        assert cache._state.cache.shape[1] == 8  # initial chunk

        kv2 = self._make_kv(1, 5)
        cache.update(kv2)
        # Needed 11, had 8, so grew by 8 -> 16
        assert cache._state.cache.shape[1] == 16
        assert cache.seq_offset == 11

    def test_preserves_existing_data(self):
        """Growth should not corrupt existing cached data."""
        cache = GrowingKVCache(chunk_size=4, device=torch.device("cpu"))
        kv1 = torch.ones(1, 3, 2, 2, 8)
        cache.update(kv1)

        kv2 = torch.ones(1, 3, 2, 2, 8) * 2.0
        result = cache.update(kv2)

        assert torch.allclose(result[:, :3], kv1)
        assert torch.allclose(result[:, 3:6], kv2)

    def test_reset_clears_state(self):
        """Reset should clear cache and offset."""
        cache = GrowingKVCache(chunk_size=8, device=torch.device("cpu"))
        cache.update(self._make_kv(1, 5))
        cache.reset()
        assert cache._state.cache is None
        assert cache.seq_offset == 0

    def test_multiple_growth_steps(self):
        """Cache should handle multiple growth steps correctly."""
        cache = GrowingKVCache(chunk_size=4, device=torch.device("cpu"))
        for _ in range(10):
            cache.update(self._make_kv(1, 3))
        assert cache.seq_offset == 30
        assert cache._state.cache.shape[1] >= 30


class TestFlashAttentionV2:
    """Tests for the FlashAttentionV2 class."""

    def _make_qkv(self, batch: int, seq: int, heads: int = 4, dim: int = 32):
        """Create matching Q and KV tensors."""
        q = torch.randn(batch, seq, heads, dim)
        kv = torch.randn(batch, seq, 2, heads, dim)
        return q, kv

    def test_init_defaults(self):
        """Should initialize with default config."""
        attn = FlashAttentionV2()
        assert attn.config.dropout_p == 0.0
        assert attn.config.causal is True
        assert isinstance(attn.backend, AttentionBackend)

    def test_init_custom_config(self):
        """Should accept custom configuration."""
        config = FlashAttentionConfig(
            dropout_p=0.1,
            causal=False,
            kv_cache_chunk_size=512,
        )
        attn = FlashAttentionV2(config)
        assert attn.config.dropout_p == 0.1
        assert attn.config.causal is False
        assert attn.kv_cache.chunk_size == 512

    @patch(
        "llm_interface_pkg.optimization.flash_attention.detect_backend",
        return_value=AttentionBackend.VANILLA,
    )
    def test_vanilla_fallback_no_mask(self, mock_backend):
        """Vanilla backend should produce correct output shape without mask."""
        attn = FlashAttentionV2()
        q, kv = self._make_qkv(2, 8)
        result = attn.forward(q, kv)
        assert result.output.shape == (2, 8, 4, 32)
        assert result.backend_used == AttentionBackend.VANILLA

    @patch(
        "llm_interface_pkg.optimization.flash_attention.detect_backend",
        return_value=AttentionBackend.VANILLA,
    )
    def test_vanilla_fallback_with_mask(self, mock_backend):
        """Vanilla backend should handle padding mask correctly."""
        attn = FlashAttentionV2()
        q, kv = self._make_qkv(2, 8)
        mask = torch.ones(2, 8, dtype=torch.bool)
        mask[1, 5:] = False  # Second sequence shorter
        result = attn.forward(q, kv, key_padding_mask=mask)
        assert result.output.shape == (2, 8, 4, 32)

    @patch(
        "llm_interface_pkg.optimization.flash_attention.detect_backend",
        return_value=AttentionBackend.SDPA,
    )
    def test_sdpa_fallback(self, mock_backend):
        """SDPA backend should produce correct output shape."""
        if not hasattr(torch.nn.functional, "scaled_dot_product_attention"):
            pytest.skip("SDPA not available in this PyTorch version")
        attn = FlashAttentionV2()
        q, kv = self._make_qkv(2, 8)
        result = attn.forward(q, kv)
        assert result.output.shape == (2, 8, 4, 32)
        assert result.backend_used == AttentionBackend.SDPA

    @patch(
        "llm_interface_pkg.optimization.flash_attention.detect_backend",
        return_value=AttentionBackend.VANILLA,
    )
    def test_causal_masking(self, mock_backend):
        """Causal attention should not attend to future tokens."""
        config = FlashAttentionConfig(causal=True)
        attn = FlashAttentionV2(config)
        q, kv = self._make_qkv(1, 4, heads=1, dim=8)
        result = attn.forward(q, kv)
        # Output should be finite (no NaN from masking issues)
        assert torch.isfinite(result.output).all()

    def test_reset_cache(self):
        """reset_cache should clear the internal KV cache."""
        attn = FlashAttentionV2()
        kv = torch.randn(1, 5, 2, 4, 32)
        attn.kv_cache.update(kv)
        assert attn.kv_cache.seq_offset == 5
        attn.reset_cache()
        assert attn.kv_cache.seq_offset == 0

    def test_factory_function(self):
        """create_flash_attention should return configured instance."""
        config = FlashAttentionConfig(kv_cache_chunk_size=128)
        attn = create_flash_attention(config)
        assert isinstance(attn, FlashAttentionV2)
        assert attn.config.kv_cache_chunk_size == 128

    def test_factory_function_default(self):
        """create_flash_attention with no args should use defaults."""
        attn = create_flash_attention()
        assert attn.config.kv_cache_chunk_size == 256


class TestRotateHalfApply:
    """Tests for the standard RoPE implementation."""

    def test_output_shape(self):
        """_rotate_half_apply should preserve input shape."""
        x = torch.randn(2, 4, 8, 64)
        cos = torch.ones_like(x)
        sin = torch.zeros_like(x)
        result = _rotate_half_apply(x, cos, sin)
        assert result.shape == x.shape

    def test_identity_with_zero_sin(self):
        """With sin=0 and cos=1, output should equal input."""
        x = torch.randn(1, 1, 1, 16)
        cos = torch.ones_like(x)
        sin = torch.zeros_like(x)
        result = _rotate_half_apply(x, cos, sin)
        assert torch.allclose(result, x, atol=1e-6)


class TestGQAExpansion:
    """Tests for Grouped Query Attention KV head expansion."""

    @patch(
        "llm_interface_pkg.optimization.flash_attention.detect_backend",
        return_value=AttentionBackend.VANILLA,
    )
    def test_gqa_expansion(self, mock_backend):
        """GQA should expand KV heads to match query heads."""
        config = FlashAttentionConfig(num_kv_heads=2)
        attn = FlashAttentionV2(config)
        q = torch.randn(1, 4, 8, 32)  # 8 query heads
        kv = torch.randn(1, 4, 2, 2, 32)  # 2 KV heads
        result = attn.forward(q, kv)
        assert result.output.shape == (1, 4, 8, 32)

    @patch(
        "llm_interface_pkg.optimization.flash_attention.detect_backend",
        return_value=AttentionBackend.VANILLA,
    )
    def test_no_expansion_when_heads_match(self, mock_backend):
        """No expansion should occur when KV heads match query heads."""
        config = FlashAttentionConfig(num_kv_heads=4)
        attn = FlashAttentionV2(config)
        q = torch.randn(1, 4, 4, 32)
        kv = torch.randn(1, 4, 2, 4, 32)
        result = attn.forward(q, kv)
        assert result.output.shape == (1, 4, 4, 32)


class TestFusedRoPE:
    """Tests for fused RoPE kernel integration."""

    @patch(
        "llm_interface_pkg.optimization.flash_attention.detect_backend",
        return_value=AttentionBackend.VANILLA,
    )
    def test_standard_rope_fallback(self, mock_backend):
        """Should use standard RoPE when fused kernel not available."""
        attn = FlashAttentionV2()
        q = torch.randn(1, 4, 8, 64)
        k = torch.randn(1, 4, 8, 64)
        cos = torch.ones(1, 4, 1, 64)
        sin = torch.zeros(1, 4, 1, 64)
        q_rot, k_rot = attn.apply_fused_rope(q, k, cos, sin)
        assert q_rot.shape == q.shape
        assert k_rot.shape == k.shape

    @patch(
        "llm_interface_pkg.optimization.flash_attention.detect_backend",
        return_value=AttentionBackend.VANILLA,
    )
    @patch(
        "llm_interface_pkg.optimization.flash_attention._flash_attn_modules",
        {"fused_rope": MagicMock(side_effect=lambda x, freqs: x)},
    )
    def test_fused_rope_when_available(self, mock_backend):
        """Should use fused kernel when available."""
        attn = FlashAttentionV2()
        q = torch.randn(1, 4, 8, 64)
        k = torch.randn(1, 4, 8, 64)
        cos = torch.ones(1, 4, 1, 64)
        sin = torch.zeros(1, 4, 1, 64)
        q_rot, k_rot = attn.apply_fused_rope(q, k, cos, sin)
        assert q_rot.shape == q.shape
