# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for only-last-logit inference optimization.

Issue #1968: Only-last-logit optimization for autoregressive generation.
"""

import types

import pytest
import torch

# Detect conftest MagicMock torch stub; skip tensor-operation tests when absent (#5737)
_TORCH_IS_STUB = not isinstance(torch, types.ModuleType)
requires_torch = pytest.mark.skipif(_TORCH_IS_STUB, reason="requires real PyTorch")

from llm_shared.optimization.inference_utils import (
    InferenceConfig,
    InferenceMode,
    LastLogitOptimizer,
    MemoryStats,
    slice_hidden_for_generation,
)


@requires_torch
class TestLastLogitOptimizer:
    """Tests for LastLogitOptimizer class."""

    def _make_hidden(self, batch: int = 1, seq_len: int = 2048, hidden_dim: int = 4096):
        """Create a dummy hidden states tensor."""
        return torch.randn(batch, seq_len, hidden_dim)

    def test_default_config_slices_for_generation(self):
        """Default config should slice in generation mode."""
        optimizer = LastLogitOptimizer()
        hidden = self._make_hidden(seq_len=2048)
        result = optimizer.slice_for_lm_head(hidden)

        assert result.was_sliced is True
        assert result.output_seq_len == 1
        assert result.original_seq_len == 2048
        assert result.hidden_states.shape == (1, 1, 4096)

    def test_last_position_logits_identical(self):
        """Sliced last-position values must match full tensor's last position."""
        hidden = self._make_hidden(batch=2, seq_len=512, hidden_dim=768)
        optimizer = LastLogitOptimizer()
        result = optimizer.slice_for_lm_head(hidden)

        expected = hidden[:, -1:, :]
        assert torch.equal(result.hidden_states, expected)

    def test_perplexity_mode_preserves_all_positions(self):
        """Perplexity mode must return full hidden states for scoring."""
        config = InferenceConfig(mode=InferenceMode.PERPLEXITY)
        optimizer = LastLogitOptimizer(config)
        hidden = self._make_hidden(seq_len=256)
        result = optimizer.slice_for_lm_head(hidden)

        assert result.was_sliced is False
        assert result.output_seq_len == 256
        assert torch.equal(result.hidden_states, hidden)

    def test_evaluation_mode_preserves_all_positions(self):
        """Evaluation mode must return full hidden states."""
        config = InferenceConfig(mode=InferenceMode.EVALUATION)
        optimizer = LastLogitOptimizer(config)
        hidden = self._make_hidden(seq_len=128)
        result = optimizer.slice_for_lm_head(hidden)

        assert result.was_sliced is False
        assert result.output_seq_len == 128

    def test_explicit_override_forces_full(self):
        """Explicit only_last_logit=False overrides generation config."""
        optimizer = LastLogitOptimizer()
        hidden = self._make_hidden(seq_len=512)
        result = optimizer.slice_for_lm_head(hidden, only_last_logit=False)

        assert result.was_sliced is False
        assert result.output_seq_len == 512

    def test_explicit_override_forces_slice(self):
        """Explicit only_last_logit=True overrides perplexity config."""
        config = InferenceConfig(mode=InferenceMode.PERPLEXITY)
        optimizer = LastLogitOptimizer(config)
        hidden = self._make_hidden(seq_len=256)
        result = optimizer.slice_for_lm_head(hidden, only_last_logit=True)

        assert result.was_sliced is True
        assert result.output_seq_len == 1

    def test_seq_len_1_no_slice(self):
        """Single-token sequences should not be sliced (already minimal)."""
        optimizer = LastLogitOptimizer()
        hidden = self._make_hidden(seq_len=1)
        result = optimizer.slice_for_lm_head(hidden)

        assert result.was_sliced is False
        assert result.output_seq_len == 1
        assert result.memory_saved_bytes == 0

    def test_memory_savings_estimation(self):
        """Memory savings should be approximately correct for fp16."""
        config = InferenceConfig(vocab_size=32000, dtype_bytes=2)
        optimizer = LastLogitOptimizer(config)
        hidden = self._make_hidden(batch=1, seq_len=2048, hidden_dim=4096)
        result = optimizer.slice_for_lm_head(hidden)

        # Expected: (2048 - 1) * 32000 * 2 = ~125 MB
        expected_bytes = 1 * 2047 * 32000 * 2
        assert result.memory_saved_bytes == expected_bytes
        assert result.memory_saved_bytes > 100 * 1024 * 1024  # > 100 MB

    def test_stats_accumulate(self):
        """Statistics should accumulate across multiple forward passes."""
        optimizer = LastLogitOptimizer()
        hidden = self._make_hidden(seq_len=512)

        optimizer.slice_for_lm_head(hidden)
        optimizer.slice_for_lm_head(hidden)
        optimizer.slice_for_lm_head(hidden, only_last_logit=False)

        assert optimizer.stats.forward_pass_count == 3
        assert optimizer.stats.sliced_count == 2
        assert optimizer.stats.total_saved_bytes > 0

    def test_reset_stats(self):
        """reset_stats should return previous stats and zero the counters."""
        optimizer = LastLogitOptimizer()
        hidden = self._make_hidden(seq_len=512)
        optimizer.slice_for_lm_head(hidden)

        previous = optimizer.reset_stats()
        assert previous.forward_pass_count == 1
        assert previous.sliced_count == 1

        assert optimizer.stats.forward_pass_count == 0
        assert optimizer.stats.sliced_count == 0
        assert optimizer.stats.total_saved_bytes == 0

    def test_invalid_dimensions_raises(self):
        """Non-3D tensors should raise ValueError."""
        optimizer = LastLogitOptimizer()
        with pytest.raises(ValueError, match="Expected 3D tensor"):
            optimizer.slice_for_lm_head(torch.randn(10, 768))

    def test_total_saved_mb_property(self):
        """MemoryStats.total_saved_mb should convert bytes correctly."""
        stats = MemoryStats(total_saved_bytes=1024 * 1024 * 50)
        assert stats.total_saved_mb == pytest.approx(50.0)


@requires_torch
class TestSliceHiddenForGeneration:
    """Tests for the convenience function."""

    def test_slices_by_default(self):
        """Default call should slice to last position."""
        hidden = torch.randn(1, 1024, 768)
        result = slice_hidden_for_generation(hidden)
        assert result.shape == (1, 1, 768)
        assert torch.equal(result, hidden[:, -1:, :])

    def test_no_slice_when_disabled(self):
        """Passing only_last_logit=False returns original tensor."""
        hidden = torch.randn(1, 1024, 768)
        result = slice_hidden_for_generation(hidden, only_last_logit=False)
        assert torch.equal(result, hidden)

    def test_no_slice_for_single_token(self):
        """Single-token input should pass through unchanged."""
        hidden = torch.randn(1, 1, 768)
        result = slice_hidden_for_generation(hidden)
        assert torch.equal(result, hidden)


class TestInferenceConfig:
    """Tests for InferenceConfig."""

    def test_generation_should_slice(self):
        """Generation mode with default flag should slice."""
        config = InferenceConfig(mode=InferenceMode.GENERATION)
        assert config.should_slice is True

    def test_generation_disabled_should_not_slice(self):
        """Generation mode with explicit disable should not slice."""
        config = InferenceConfig(mode=InferenceMode.GENERATION, only_last_logit=False)
        assert config.should_slice is False

    def test_perplexity_should_not_slice(self):
        """Perplexity mode should never slice regardless of flag."""
        config = InferenceConfig(mode=InferenceMode.PERPLEXITY, only_last_logit=True)
        assert config.should_slice is False

    def test_evaluation_should_not_slice(self):
        """Evaluation mode should never slice regardless of flag."""
        config = InferenceConfig(mode=InferenceMode.EVALUATION, only_last_logit=True)
        assert config.should_slice is False
