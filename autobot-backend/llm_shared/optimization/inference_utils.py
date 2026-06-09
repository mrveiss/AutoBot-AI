# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Inference Utilities - Only-last-logit optimization for autoregressive generation.

During autoregressive generation, only the last token position's logits determine
the next token. Computing the full vocabulary projection (lm_head) for all positions
is wasteful. This module provides utilities to slice hidden states before projection,
yielding up to 2048x reduction in the final projection computation.

Issue #1968: Only-last-logit optimization for autoregressive generation.
"""

from dataclasses import dataclass
from enum import Enum

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Conditional torch import — module degrades gracefully without it
try:
    import torch
except (ImportError, RuntimeError):
    torch = None  # type: ignore[assignment]


class InferenceMode(str, Enum):
    """Inference mode controlling logit computation scope."""

    GENERATION = "generation"
    PERPLEXITY = "perplexity"
    EVALUATION = "evaluation"


@dataclass
class LogitSliceResult:
    """Result of a logit slicing operation.

    Attributes:
        hidden_states: The (possibly sliced) hidden states ready for lm_head.
        was_sliced: Whether the hidden states were sliced to last position.
        original_seq_len: Original sequence length before slicing.
        output_seq_len: Sequence length after slicing.
        memory_saved_bytes: Estimated memory saved by slicing (bytes).
    """

    hidden_states: "torch.Tensor"
    was_sliced: bool
    original_seq_len: int
    output_seq_len: int
    memory_saved_bytes: int


@dataclass
class InferenceConfig:
    """Configuration for inference optimization.

    Attributes:
        only_last_logit: Slice to last position for generation (default True).
        mode: Inference mode controlling default behavior.
        vocab_size: Vocabulary size for memory estimation.
        dtype_bytes: Bytes per element for memory estimation (2=fp16, 4=fp32).
    """

    only_last_logit: bool = True
    mode: InferenceMode = InferenceMode.GENERATION
    vocab_size: int = 32000
    dtype_bytes: int = 2

    @property
    def should_slice(self) -> bool:
        """Determine whether to slice based on mode and explicit flag."""
        if self.mode in (InferenceMode.PERPLEXITY, InferenceMode.EVALUATION):
            return False
        return self.only_last_logit


@dataclass
class MemoryStats:
    """Cumulative memory savings statistics.

    Attributes:
        total_saved_bytes: Total bytes saved across all forward passes.
        forward_pass_count: Number of forward passes processed.
        sliced_count: Number of passes where slicing was applied.
    """

    total_saved_bytes: int = 0
    forward_pass_count: int = 0
    sliced_count: int = 0

    @property
    def total_saved_mb(self) -> float:
        """Total memory saved in megabytes."""
        return self.total_saved_bytes / (1024 * 1024)


class LastLogitOptimizer:
    """Optimizer that slices hidden states to last position before lm_head projection.

    For autoregressive generation, only the last token position determines the
    next token. By slicing hidden_states[:, -1:, :] before the lm_head linear
    layer, we avoid computing vocab_size logits for all other positions.

    Savings example (seq_len=2048, vocab_size=32000, fp16):
        Full:    batch * 2048 * 32000 * 2 bytes = ~125 MB
        Sliced:  batch * 1    * 32000 * 2 bytes = ~62 KB

    Issue #1968.
    """

    def __init__(self, config: InferenceConfig | None = None):
        """Initialize with optional configuration.

        Args:
            config: Inference configuration. Defaults to generation mode.
        """
        self._config = config or InferenceConfig()
        self._stats = MemoryStats()

    @property
    def config(self) -> InferenceConfig:
        """Current inference configuration."""
        return self._config

    @property
    def stats(self) -> MemoryStats:
        """Cumulative memory savings statistics."""
        return self._stats

    def slice_for_lm_head(
        self,
        hidden_states: "torch.Tensor",
        only_last_logit: bool | None = None,
    ) -> LogitSliceResult:
        """Slice hidden states to last position for efficient lm_head projection.

        Args:
            hidden_states: Model hidden states [batch, seq_len, hidden_dim].
            only_last_logit: Override config's only_last_logit setting.
                None uses the config default.

        Returns:
            LogitSliceResult with sliced (or unmodified) hidden states.

        Raises:
            ValueError: If hidden_states does not have 3 dimensions.
        """
        if torch is None:
            raise RuntimeError("PyTorch is required for LastLogitOptimizer")

        if hidden_states.ndim != 3:
            raise ValueError(f"Expected 3D tensor [batch, seq_len, hidden_dim], " f"got {hidden_states.ndim}D")

        batch_size, seq_len, hidden_dim = hidden_states.shape
        should_slice = only_last_logit if only_last_logit is not None else self._config.should_slice

        self._stats.forward_pass_count += 1

        if should_slice and seq_len > 1:
            sliced = hidden_states[:, -1:, :]
            saved = self._estimate_memory_saved(batch_size, seq_len, hidden_dim)
            self._stats.total_saved_bytes += saved
            self._stats.sliced_count += 1

            logger.debug(
                "Last-logit slice: seq_len %d -> 1, saved ~%.2f MB",
                seq_len,
                saved / (1024 * 1024),
            )

            return LogitSliceResult(
                hidden_states=sliced,
                was_sliced=True,
                original_seq_len=seq_len,
                output_seq_len=1,
                memory_saved_bytes=saved,
            )

        return LogitSliceResult(
            hidden_states=hidden_states,
            was_sliced=False,
            original_seq_len=seq_len,
            output_seq_len=seq_len,
            memory_saved_bytes=0,
        )

    def _estimate_memory_saved(self, batch_size: int, seq_len: int, hidden_dim: int) -> int:
        """Estimate bytes saved by slicing hidden states before lm_head.

        The lm_head output is [batch, seq_len, vocab_size]. Slicing reduces
        seq_len to 1, saving (seq_len - 1) / seq_len of the output memory.

        Args:
            batch_size: Batch size.
            seq_len: Original sequence length.
            hidden_dim: Hidden dimension (unused in output calc, kept for API).

        Returns:
            Estimated bytes saved.
        """
        full_output_bytes = batch_size * seq_len * self._config.vocab_size * self._config.dtype_bytes
        sliced_output_bytes = batch_size * 1 * self._config.vocab_size * self._config.dtype_bytes
        return full_output_bytes - sliced_output_bytes

    def reset_stats(self) -> MemoryStats:
        """Reset and return the accumulated statistics.

        Returns:
            The stats as they were before resetting.
        """
        previous = MemoryStats(
            total_saved_bytes=self._stats.total_saved_bytes,
            forward_pass_count=self._stats.forward_pass_count,
            sliced_count=self._stats.sliced_count,
        )
        self._stats = MemoryStats()
        return previous


def slice_hidden_for_generation(
    hidden_states: "torch.Tensor",
    only_last_logit: bool = True,
) -> "torch.Tensor":
    """Convenience function: slice hidden states for generation.

    Stateless version for simple use cases that don't need tracking.

    Args:
        hidden_states: Model hidden states [batch, seq_len, hidden_dim].
        only_last_logit: If True, return only last position.

    Returns:
        Sliced or original hidden states tensor.

    Issue #1968.
    """
    if only_last_logit and hidden_states.ndim == 3 and hidden_states.shape[1] > 1:
        return hidden_states[:, -1:, :]
    return hidden_states


__all__ = [
    "InferenceConfig",
    "InferenceMode",
    "LastLogitOptimizer",
    "LogitSliceResult",
    "MemoryStats",
    "slice_hidden_for_generation",
]
