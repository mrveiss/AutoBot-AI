# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Flash Attention v2 with variable-length sequence optimization.

Provides padded and unpadded attention paths for batch inference,
using unpadding to avoid wasting GPU compute on padding tokens.
Includes fused RoPE kernel, growing KV cache, and JIT-compiled
GQA expansion. Graceful fallback: Flash Attn -> SDPA -> vanilla.

Issue #1955: Flash Attention v2 with variable-length sequence optimization.
"""

# Issue #3009: from __future__ import annotations defers annotation evaluation
# so torch types in dataclass fields / function signatures are strings at runtime.
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Tuple

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    import torch  # noqa: F401  # used by deferred (string) type annotations

logger = get_logger(__name__)

# Issue #3009: Lazy-load torch on first use so importing this module does not
# require torch to be installed (NPU/GPU subsystem is feature-flagged).
_torch: Any = None


def _get_torch() -> Any:
    """Return the torch module, importing it on first call."""
    global _torch  # noqa: PLW0603
    if _torch is None:
        import torch

        _torch = torch
    return _torch


# Lazy imports for optional dependencies
_flash_attn_available: bool | None = None
_flash_attn_modules: dict = {}


class AttentionBackend(Enum):
    """Available attention computation backends."""

    FLASH_ATTN_V2 = "flash_attn_v2"
    SDPA = "sdpa"
    VANILLA = "vanilla"


@dataclass
class FlashAttentionConfig:
    """Configuration for Flash Attention v2.

    Attributes:
        dropout_p: Dropout probability during training (0.0 for inference).
        softmax_scale: Scaling factor for QK^T. None = 1/sqrt(head_dim).
        causal: Whether to apply causal masking.
        kv_cache_chunk_size: Grow KV cache by this many positions at a time.
        num_kv_heads: Number of key-value heads (for GQA). None = same as query heads.
        max_sequence_length: Maximum expected sequence length for cache pre-allocation.
    """

    dropout_p: float = 0.0
    softmax_scale: float | None = None
    causal: bool = True
    kv_cache_chunk_size: int = 256
    num_kv_heads: int | None = None
    max_sequence_length: int = 8192


@dataclass
class AttentionOutput:
    """Result of an attention computation.

    Attributes:
        output: The attention output tensor [batch, seq_len, num_heads, head_dim].
        backend_used: Which backend actually executed the computation.
    """

    output: torch.Tensor
    backend_used: AttentionBackend


@dataclass
class KVCacheState:
    """Growing KV cache state for incremental decoding.

    Issue #1955: Grows in chunks to reduce allocation overhead.

    Attributes:
        cache: The KV cache tensor or None if uninitialized.
        seq_offset: Current position in the cache (number of filled positions).
        chunk_size: Number of positions to grow by when cache is full.
    """

    cache: torch.Tensor | None = None
    seq_offset: int = 0
    chunk_size: int = 256


def _probe_flash_attn() -> bool:
    """Check if flash_attn package is available and load modules lazily."""
    global _flash_attn_available  # noqa: PLW0603
    if _flash_attn_available is not None:
        return _flash_attn_available

    try:
        from flash_attn import flash_attn_kvpacked_func, flash_attn_varlen_kvpacked_func
        from flash_attn.bert_padding import pad_input, unpad_input

        _flash_attn_modules["flash_attn_kvpacked_func"] = flash_attn_kvpacked_func
        _flash_attn_modules["flash_attn_varlen_kvpacked_func"] = flash_attn_varlen_kvpacked_func
        _flash_attn_modules["unpad_input"] = unpad_input
        _flash_attn_modules["pad_input"] = pad_input
        _flash_attn_available = True
        logger.info("Flash Attention v2 loaded successfully")
    except (ImportError, RuntimeError):
        _flash_attn_available = False
        logger.info("flash_attn not available, will use fallback backends")

    _try_load_fused_rope()
    return _flash_attn_available


def _try_load_fused_rope() -> None:
    """Attempt to load fused RoPE kernel from flash_attn."""
    try:
        from flash_attn.layers.rotary import apply_rotary_emb as fused_rope

        _flash_attn_modules["fused_rope"] = fused_rope
        logger.info("Fused RoPE kernel loaded from flash_attn")
    except (ImportError, RuntimeError):
        logger.debug("Fused RoPE kernel not available, using standard implementation")


def _has_sdpa() -> bool:
    """Check if PyTorch scaled_dot_product_attention is available."""
    return hasattr(_get_torch().nn.functional, "scaled_dot_product_attention")


def detect_backend() -> AttentionBackend:
    """Detect the best available attention backend.

    Returns:
        The highest-tier available backend.
    """
    if _probe_flash_attn():
        return AttentionBackend.FLASH_ATTN_V2
    if _has_sdpa():
        return AttentionBackend.SDPA
    return AttentionBackend.VANILLA


def _build_repeat_kv_fn():
    """Build a JIT-compiled repeat_kv function for GQA expansion.

    Issue #1955: JIT compilation avoids Python overhead on repeated calls.
    Issue #3009: torch imported lazily — only called after torch is available.
    """
    import torch  # noqa: PLC0415 — lazy import, torch is a heavy optional dep

    @torch.jit.script
    def repeat_kv(kv: torch.Tensor, n_rep: int) -> torch.Tensor:
        """Expand KV heads for Grouped Query Attention.

        Args:
            kv: Key or value tensor [batch, seq_len, num_kv_heads, head_dim].
            n_rep: Number of times to repeat each KV head.

        Returns:
            Expanded tensor [batch, seq_len, num_kv_heads * n_rep, head_dim].
        """
        if n_rep == 1:
            return kv
        batch, seq_len, num_kv_heads, head_dim = kv.shape
        kv = kv[:, :, :, None, :].expand(batch, seq_len, num_kv_heads, n_rep, head_dim)
        return kv.reshape(batch, seq_len, num_kv_heads * n_rep, head_dim)

    return repeat_kv


# Issue #3009: repeat_kv is built lazily on first use so that importing this
# module does not trigger a torch import at startup.
_repeat_kv_fn = None


def repeat_kv(kv: Any, n_rep: int) -> Any:
    """Expand KV heads for GQA — thin wrapper around the JIT-compiled version."""
    global _repeat_kv_fn  # noqa: PLW0603
    if _repeat_kv_fn is None:
        _repeat_kv_fn = _build_repeat_kv_fn()
    return _repeat_kv_fn(kv, n_rep)


class GrowingKVCache:
    """KV cache that grows in fixed-size chunks to reduce allocation overhead.

    Issue #1955: Instead of reallocating per token, extends by chunk_size
    positions at a time using torch.cat with pre-allocated empty tensors.

    Args:
        chunk_size: Number of positions to add per growth step.
        device: Torch device for cache tensors.
        dtype: Torch dtype for cache tensors.
    """

    def __init__(
        self,
        chunk_size: int = 256,
        device: torch.device | None = None,
        dtype: torch.dtype = None,
    ):
        _t = _get_torch()
        self.chunk_size = chunk_size
        self.device = device or _t.device("cuda" if _t.cuda.is_available() else "cpu")
        self.dtype = dtype if dtype is not None else _t.float16
        self._state = KVCacheState(chunk_size=chunk_size)

    @property
    def seq_offset(self) -> int:
        """Current number of filled positions in the cache."""
        return self._state.seq_offset

    def update(self, new_kv: torch.Tensor) -> torch.Tensor:
        """Append new KV entries to the cache, growing if needed.

        Args:
            new_kv: New key-value tensor [batch, new_seq, 2, num_heads, head_dim].

        Returns:
            Full KV cache up to current position [batch, total_seq, 2, num_heads, head_dim].
        """
        new_seq_len = new_kv.shape[1]

        if self._state.cache is None:
            self._state.cache = self._allocate_initial(new_kv)

        needed = self._state.seq_offset + new_seq_len
        self._grow_if_needed(new_kv, needed)
        self._write_entries(new_kv, new_seq_len)

        return self._state.cache[:, : self._state.seq_offset]

    def _allocate_initial(self, new_kv: torch.Tensor) -> torch.Tensor:
        """Allocate the initial cache with chunk-aligned capacity."""
        batch, _, kv_pair, num_heads, head_dim = new_kv.shape
        initial_len = self.chunk_size
        return _get_torch().zeros(
            batch,
            initial_len,
            kv_pair,
            num_heads,
            head_dim,
            device=self.device,
            dtype=self.dtype,
        )

    def _grow_if_needed(self, new_kv: torch.Tensor, needed: int) -> None:
        """Grow cache capacity in chunk increments if needed."""
        current_capacity = self._state.cache.shape[1]
        if needed <= current_capacity:
            return

        extra_chunks = ((needed - current_capacity - 1) // self.chunk_size) + 1
        extra_len = extra_chunks * self.chunk_size
        batch, _, kv_pair, num_heads, head_dim = new_kv.shape
        _t = _get_torch()
        extension = _t.zeros(
            batch,
            extra_len,
            kv_pair,
            num_heads,
            head_dim,
            device=self.device,
            dtype=self.dtype,
        )
        self._state.cache = _t.cat([self._state.cache, extension], dim=1)
        logger.debug(
            "KV cache grown by %d positions to %d total",
            extra_len,
            self._state.cache.shape[1],
        )

    def _write_entries(self, new_kv: torch.Tensor, new_seq_len: int) -> None:
        """Write new entries into the cache at current offset."""
        start = self._state.seq_offset
        end = start + new_seq_len
        self._state.cache[:, start:end] = new_kv
        self._state.seq_offset = end

    def reset(self) -> None:
        """Clear the cache for a new sequence."""
        self._state = KVCacheState(chunk_size=self.chunk_size)


# ARCHITECTURE_EXCEPTION: "FlashAttentionV2" retains the V2 suffix because
# "FlashAttention-2" is the published algorithm name (Dao et al., 2023).
# The suffix denotes the algorithm version, not an internal code iteration.
class FlashAttentionV2:
    """Flash Attention v2 with variable-length sequence optimization.

    Provides two paths:
    - Padded path: standard flash_attn_kvpacked_func (no padding mask needed)
    - Unpadded path: unpad -> flash_attn_varlen_kvpacked_func -> pad
      for batches with mixed sequence lengths

    Falls back to SDPA or vanilla attention when flash_attn is not installed.

    Issue #1955.

    Args:
        config: Flash attention configuration.
    """

    def __init__(self, config: FlashAttentionConfig | None = None):
        self.config = config or FlashAttentionConfig()
        self.backend = detect_backend()
        self.kv_cache = GrowingKVCache(
            chunk_size=self.config.kv_cache_chunk_size,
        )
        logger.info("FlashAttentionV2 initialized with backend=%s", self.backend.value)

    def forward(
        self,
        q: torch.Tensor,
        kv: torch.Tensor,
        key_padding_mask: torch.Tensor | None = None,
    ) -> AttentionOutput:
        """Run attention with automatic backend and path selection.

        Args:
            q: Query tensor [batch, seq_len, num_heads, head_dim].
            kv: Key-value tensor [batch, seq_len, 2, num_kv_heads, head_dim].
            key_padding_mask: Boolean mask [batch, seq_len] where True = valid token.
                None means no padding (all tokens valid).

        Returns:
            AttentionOutput with result tensor and backend used.
        """
        if self.config.num_kv_heads is not None:
            kv = self._expand_kv_for_gqa(q, kv)

        if self.backend == AttentionBackend.FLASH_ATTN_V2:
            return self._forward_flash(q, kv, key_padding_mask)
        if self.backend == AttentionBackend.SDPA:
            return self._forward_sdpa(q, kv, key_padding_mask)
        return self._forward_vanilla(q, kv, key_padding_mask)

    def _expand_kv_for_gqa(self, q: torch.Tensor, kv: torch.Tensor) -> torch.Tensor:
        """Expand KV heads to match query heads for GQA models."""
        num_q_heads = q.shape[2]
        num_kv_heads = kv.shape[3]
        if num_q_heads == num_kv_heads:
            return kv
        n_rep = num_q_heads // num_kv_heads
        k = repeat_kv(kv[:, :, 0], n_rep)
        v = repeat_kv(kv[:, :, 1], n_rep)
        return _get_torch().stack([k, v], dim=2)

    def _forward_flash(
        self,
        q: torch.Tensor,
        kv: torch.Tensor,
        key_padding_mask: torch.Tensor | None,
    ) -> AttentionOutput:
        """Execute using Flash Attention v2 backend."""
        if key_padding_mask is None:
            output = self._flash_padded(q, kv)
        else:
            output = self._flash_unpadded(q, kv, key_padding_mask)
        return AttentionOutput(output=output, backend_used=AttentionBackend.FLASH_ATTN_V2)

    def _flash_padded(self, q: torch.Tensor, kv: torch.Tensor) -> torch.Tensor:
        """Fastest path: no padding mask needed.

        Issue #1955: Direct call to flash_attn_kvpacked_func.
        """
        flash_fn = _flash_attn_modules["flash_attn_kvpacked_func"]
        return flash_fn(
            q,
            kv,
            dropout_p=self.config.dropout_p,
            softmax_scale=self.config.softmax_scale,
            causal=self.config.causal,
        )

    def _flash_unpadded(
        self,
        q: torch.Tensor,
        kv: torch.Tensor,
        key_padding_mask: torch.Tensor,
    ) -> torch.Tensor:
        """Variable-length path: unpad -> compute -> repad.

        Issue #1955: Avoids wasting GPU compute on padding tokens by using
        flash_attn_varlen_kvpacked_func with cumulative sequence lengths.
        """
        unpad_fn = _flash_attn_modules["unpad_input"]
        pad_fn = _flash_attn_modules["pad_input"]
        varlen_fn = _flash_attn_modules["flash_attn_varlen_kvpacked_func"]

        batch_size = q.shape[0]
        q_unpad, indices_q, cu_seqlens_q, max_seqlen_q = unpad_fn(
            q.reshape(batch_size, -1, q.shape[-2] * q.shape[-1]),
            key_padding_mask,
        )
        q_unpad = q_unpad.reshape(-1, q.shape[-2], q.shape[-1])

        kv_flat = kv.reshape(batch_size, -1, 2 * kv.shape[-2] * kv.shape[-1])
        kv_unpad, _indices_kv, cu_seqlens_k, max_seqlen_k = unpad_fn(
            kv_flat,
            key_padding_mask,
        )
        kv_unpad = kv_unpad.reshape(-1, 2, kv.shape[-2], kv.shape[-1])

        output_unpad = varlen_fn(
            q_unpad,
            kv_unpad,
            cu_seqlens_q,
            cu_seqlens_k,
            max_seqlen_q,
            max_seqlen_k,
            dropout_p=self.config.dropout_p,
            softmax_scale=self.config.softmax_scale,
            causal=self.config.causal,
        )

        output_flat = output_unpad.reshape(-1, q.shape[-2] * q.shape[-1])
        output = pad_fn(output_flat, indices_q, batch_size, max_seqlen_q)
        return output.reshape(batch_size, -1, q.shape[-2], q.shape[-1])

    def _forward_sdpa(
        self,
        q: torch.Tensor,
        kv: torch.Tensor,
        key_padding_mask: torch.Tensor | None,
    ) -> AttentionOutput:
        """Fallback: PyTorch scaled_dot_product_attention.

        Issue #1955: Second-tier fallback when flash_attn is not installed.
        """
        k, v = kv[:, :, 0], kv[:, :, 1]
        q_t = q.transpose(1, 2)
        k_t = k.transpose(1, 2)
        v_t = v.transpose(1, 2)

        attn_mask = self._build_sdpa_mask(key_padding_mask, q.shape[1], q.device)

        output = _get_torch().nn.functional.scaled_dot_product_attention(
            q_t,
            k_t,
            v_t,
            attn_mask=attn_mask,
            dropout_p=self.config.dropout_p if self.training else 0.0,
            is_causal=self.config.causal and attn_mask is None,
        )
        return AttentionOutput(
            output=output.transpose(1, 2),
            backend_used=AttentionBackend.SDPA,
        )

    def _build_sdpa_mask(
        self,
        key_padding_mask: torch.Tensor | None,
        seq_len: int,
        device: torch.device,
    ) -> torch.Tensor | None:
        """Build combined causal + padding mask for SDPA."""
        if key_padding_mask is None and not self.config.causal:
            return None

        mask = None
        if self.config.causal and key_padding_mask is not None:
            _t = _get_torch()
            causal = _t.tril(_t.ones(seq_len, seq_len, device=device, dtype=_t.bool))
            pad_mask = key_padding_mask[:, None, None, :]
            mask = causal[None, None, :, :] & pad_mask
        elif key_padding_mask is not None:
            mask = key_padding_mask[:, None, None, :]

        return mask

    def _forward_vanilla(
        self,
        q: torch.Tensor,
        kv: torch.Tensor,
        key_padding_mask: torch.Tensor | None,
    ) -> AttentionOutput:
        """Lowest-tier fallback: manual scaled dot-product attention.

        Issue #1955: Vanilla implementation for environments without
        flash_attn or SDPA support.
        """
        k, v = kv[:, :, 0], kv[:, :, 1]
        head_dim = q.shape[-1]
        scale = self.config.softmax_scale or (head_dim**-0.5)

        q_t = q.transpose(1, 2)
        k_t = k.transpose(1, 2)
        v_t = v.transpose(1, 2)

        _t = _get_torch()
        scores = _t.matmul(q_t, k_t.transpose(-2, -1)) * scale
        scores = self._apply_masks_to_scores(scores, key_padding_mask, q.shape[1], q.device)
        weights = _t.softmax(scores, dim=-1)

        output = _t.matmul(weights, v_t)
        return AttentionOutput(
            output=output.transpose(1, 2),
            backend_used=AttentionBackend.VANILLA,
        )

    def _apply_masks_to_scores(
        self,
        scores: torch.Tensor,
        key_padding_mask: torch.Tensor | None,
        seq_len: int,
        device: torch.device,
    ) -> torch.Tensor:
        """Apply causal and padding masks to attention scores."""
        if self.config.causal:
            _t = _get_torch()
            causal_mask = _t.triu(
                _t.ones(seq_len, seq_len, device=device, dtype=_t.bool),
                diagonal=1,
            )
            scores = scores.masked_fill(causal_mask[None, None, :, :], float("-inf"))

        if key_padding_mask is not None:
            pad_mask = ~key_padding_mask[:, None, None, :]
            scores = scores.masked_fill(pad_mask, float("-inf"))

        return scores

    @property
    def training(self) -> bool:
        """Whether the module is in training mode (always False for inference)."""
        return False

    def apply_fused_rope(
        self,
        q: torch.Tensor,
        k: torch.Tensor,
        cos: torch.Tensor,
        sin: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Apply rotary position embedding using fused kernel if available.

        Issue #1955: Fused RoPE avoids a separate kernel launch.

        Args:
            q: Query tensor.
            k: Key tensor.
            cos: Cosine frequencies.
            sin: Sine frequencies.

        Returns:
            Tuple of (rotated_q, rotated_k).
        """
        fused_rope_fn = _flash_attn_modules.get("fused_rope")
        if fused_rope_fn is not None:
            return self._apply_fused_rope_kernel(fused_rope_fn, q, k, cos, sin)
        return self._apply_standard_rope(q, k, cos, sin)

    def _apply_fused_rope_kernel(
        self,
        fused_fn,
        q: torch.Tensor,
        k: torch.Tensor,
        cos: torch.Tensor,
        sin: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Apply RoPE using the fused flash_attn kernel."""
        freqs = _get_torch().stack([cos, sin], dim=-1)
        q_rot = fused_fn(q, freqs)
        k_rot = fused_fn(k, freqs)
        return q_rot, k_rot

    @staticmethod
    def _apply_standard_rope(
        q: torch.Tensor,
        k: torch.Tensor,
        cos: torch.Tensor,
        sin: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Standard RoPE implementation as fallback."""
        q_rot = _rotate_half_apply(q, cos, sin)
        k_rot = _rotate_half_apply(k, cos, sin)
        return q_rot, k_rot

    def reset_cache(self) -> None:
        """Reset the KV cache for a new generation sequence."""
        self.kv_cache.reset()


def _rotate_half_apply(
    x: torch.Tensor,
    cos: torch.Tensor,
    sin: torch.Tensor,
) -> torch.Tensor:
    """Apply rotary embedding to a tensor using the rotate-half method.

    Args:
        x: Input tensor [..., head_dim].
        cos: Cosine frequencies, broadcastable to x.
        sin: Sine frequencies, broadcastable to x.

    Returns:
        Rotated tensor with same shape as x.
    """
    half = x.shape[-1] // 2
    x1, x2 = x[..., :half], x[..., half:]
    rotated = _get_torch().cat([-x2, x1], dim=-1)
    return x * cos + rotated * sin


def create_flash_attention(
    config: FlashAttentionConfig | None = None,
) -> FlashAttentionV2:
    """Factory function to create a FlashAttentionV2 instance.

    Issue #1955.

    Args:
        config: Optional configuration. Uses defaults if None.

    Returns:
        Configured FlashAttentionV2 instance.
    """
    return FlashAttentionV2(config)


__all__ = [
    "AttentionBackend",
    "AttentionOutput",
    "FlashAttentionConfig",
    "FlashAttentionV2",
    "GrowingKVCache",
    "KVCacheState",
    "create_flash_attention",
    "detect_backend",
    "repeat_kv",
]
