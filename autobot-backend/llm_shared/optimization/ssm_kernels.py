# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Non-attention sequence-mixing kernels: SSM selective-scan, linear attention,
and Jamba-style hybrid per-layer routing.

These are the concrete compute kernels selected by
:mod:`attention_backend` for non-transformer architecture families
(``STATE_SPACE``, ``LINEAR_ATTENTION``, ``HYBRID``).  They mirror the
kernel-invocation pattern of :mod:`flash_attention` (lazy torch import,
dataclass config, real ``forward``), but implement recurrent / linear
sequence mixers rather than scaled-dot-product attention.

Kernels (Issue #10724)
  SSMScanKernel        — Mamba-style selective scan h_t = A_t·h_{t-1} + B_t·x_t,
                         y_t = C_t·h_t (O(L) recurrence over (B, L, D)).
  LinearAttentionKernel— feature-map linear attention φ(Q)(φ(K)ᵀV) giving O(L)
                         instead of O(L²); includes the causal cumulative form.
  HybridRouter         — per-layer dispatch: attention layers → the caller's
                         attention path; SSM layers → SSMScanKernel.

Heavy torch is imported lazily so the module loads without torch installed;
callers on a torch-less host receive an ImportError only when they actually
invoke a kernel.

Issue #10724: real SSM/linear/hybrid kernels replacing NOT_APPLICABLE stubs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, List

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    import torch  # noqa: F401 — used by deferred (string) annotations

logger = get_logger(__name__)

_torch: Any = None


def _get_torch() -> Any:
    """Return the torch module, importing it lazily on first use."""
    global _torch  # noqa: PLW0603
    if _torch is None:
        try:
            import torch  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise ImportError(
                "torch is required for SSM/linear/hybrid kernels. Install with: pip install torch>=2.0.0"
            ) from exc
        _torch = torch
    return _torch


class LayerKind(str, Enum):
    """Per-layer sequence-mixer kind used by :class:`HybridRouter`."""

    ATTENTION = "attention"
    SSM = "ssm"


# ---------------------------------------------------------------------------
# Feature maps for linear attention
# ---------------------------------------------------------------------------


def elu_feature_map(x: Any) -> Any:
    """Standard ``elu(x) + 1`` positive feature map φ (Katharopoulos et al. 2020).

    Guarantees strictly-positive features so denominators never vanish.

    Args:
        x: Tensor ``[..., dim]``.

    Returns:
        Tensor of the same shape with φ applied elementwise.
    """
    torch = _get_torch()
    return torch.nn.functional.elu(x) + 1.0


# ---------------------------------------------------------------------------
# SSM selective scan (Mamba-style)
# ---------------------------------------------------------------------------


@dataclass
class SSMConfig:
    """Configuration for the selective-scan kernel.

    Attributes:
        clamp_dt: Lower bound applied to Δ before discretisation to keep the
            recurrence numerically stable (Δ must be positive).
    """

    clamp_dt: float = 1e-4


class SSMScanKernel:
    """Mamba-style selective state-space scan over ``(B, L, D)`` sequences.

    Implements the diagonal selective-scan recurrence

        Ā_t = exp(Δ_t · A)                    (zero-order hold discretisation)
        B̄_t = Δ_t · B_t
        h_t  = Ā_t ⊙ h_{t-1} + B̄_t ⊙ x_t
        y_t  = Σ_n C_t,n · h_t,n              (contract over state dim N)

    with a per-position, per-channel state of shape ``(B, D, N)``.  ``A`` is a
    diagonal (negative) state matrix ``(D, N)``; ``B``/``C`` are input/output
    projections ``(B, L, N)``; ``Δ`` is the per-token step ``(B, L, D)``.

    The scan is an explicit O(L) recurrence — correctness over raw speed, and
    directly testable against a naive reference.

    Args:
        config: Optional :class:`SSMConfig`.
    """

    def __init__(self, config: SSMConfig | None = None) -> None:
        self.config = config or SSMConfig()

    def forward(self, x: Any, a: Any, b: Any, c: Any, delta: Any) -> Any:
        """Run the selective scan and return ``y`` of shape ``(B, L, D)``.

        Args:
            x: Input sequence ``(B, L, D)``.
            a: Diagonal state matrix ``(D, N)`` (typically negative).
            b: Input projection ``(B, L, N)``.
            c: Output projection ``(B, L, N)``.
            delta: Per-token step size ``(B, L, D)`` (made positive via softplus).
        """
        torch = _get_torch()
        dt = torch.nn.functional.softplus(delta).clamp_min(self.config.clamp_dt)
        a_bar = torch.exp(dt.unsqueeze(-1) * a)  # (B, L, D, N)
        bx = self._input_term(dt, b, x)  # (B, L, D, N)
        return self._scan(a_bar, bx, c)

    @staticmethod
    def _input_term(dt: Any, b: Any, x: Any) -> Any:
        """Compute B̄_t ⊙ x_t = (Δ_t · B_t) ⊗ x_t as ``(B, L, D, N)``."""
        b_bar = dt.unsqueeze(-1) * b.unsqueeze(2)  # (B, L, D, N)
        return b_bar * x.unsqueeze(-1)

    def _scan(self, a_bar: Any, bx: Any, c: Any) -> Any:
        """Sequential recurrence over L; returns ``y`` of shape ``(B, L, D)``."""
        torch = _get_torch()
        batch, length, dim, _n = a_bar.shape
        h = torch.zeros(batch, dim, a_bar.shape[-1], dtype=a_bar.dtype, device=a_bar.device)
        outputs: List[Any] = []
        for t in range(length):
            h = a_bar[:, t] * h + bx[:, t]  # (B, D, N)
            y_t = torch.einsum("bdn,bn->bd", h, c[:, t])  # contract state dim
            outputs.append(y_t)
        return torch.stack(outputs, dim=1)


# ---------------------------------------------------------------------------
# Linear attention
# ---------------------------------------------------------------------------


@dataclass
class LinearAttentionConfig:
    """Configuration for the linear-attention kernel.

    Attributes:
        causal: Whether to apply causal (autoregressive) masking via the
            cumulative-sum recurrence.
        eps: Numerical floor added to the normaliser denominator.
    """

    causal: bool = False
    eps: float = 1e-6


class LinearAttentionKernel:
    """Feature-map linear attention with O(L) associativity.

    Non-causal form computes, per head,

        KV = φ(K)ᵀ V                 (D_k × D_v)
        Z  = Σ_t φ(K_t)              (D_k)
        Y_t = φ(Q_t) · KV / (φ(Q_t) · Z)

    which is algebraically identical to the direct softmax-free attention
    ``(φ(Q) φ(K)ᵀ) V`` normalised by ``φ(Q) φ(K)ᵀ 1`` but costs O(L·D²) rather
    than O(L²·D).  The causal variant replaces the global sums with running
    (cumulative) sums so position ``t`` only attends to ``≤ t``.

    Tensors are ``(B, H, L, D)``.

    Args:
        config: Optional :class:`LinearAttentionConfig`.
    """

    def __init__(self, config: LinearAttentionConfig | None = None) -> None:
        self.config = config or LinearAttentionConfig()
        self._phi: Callable[[Any], Any] = elu_feature_map

    def forward(self, q: Any, k: Any, v: Any) -> Any:
        """Return the linear-attention output ``(B, H, L, D_v)``."""
        phi_q = self._phi(q)
        phi_k = self._phi(k)
        if self.config.causal:
            return self._causal(phi_q, phi_k, v)
        return self._non_causal(phi_q, phi_k, v)

    def _non_causal(self, phi_q: Any, phi_k: Any, v: Any) -> Any:
        """Global-sum associative form (O(L))."""
        torch = _get_torch()
        kv = torch.einsum("bhld,bhle->bhde", phi_k, v)  # (B, H, D_k, D_v)
        numerator = torch.einsum("bhld,bhde->bhle", phi_q, kv)
        z = phi_k.sum(dim=2)  # (B, H, D_k)
        denom = torch.einsum("bhld,bhd->bhl", phi_q, z).clamp_min(self.config.eps)
        return numerator / denom.unsqueeze(-1)

    def _causal(self, phi_q: Any, phi_k: Any, v: Any) -> Any:
        """Causal cumulative-sum form; position t attends to ≤ t only."""
        torch = _get_torch()
        kv = torch.einsum("bhld,bhle->bhlde", phi_k, v)  # per-step outer products
        kv_cumsum = kv.cumsum(dim=2)  # running KV state
        numerator = torch.einsum("bhld,bhlde->bhle", phi_q, kv_cumsum)
        z_cumsum = phi_k.cumsum(dim=2)  # running key sum
        denom = torch.einsum("bhld,bhld->bhl", phi_q, z_cumsum).clamp_min(self.config.eps)
        return numerator / denom.unsqueeze(-1)


# ---------------------------------------------------------------------------
# Hybrid (Jamba-style) per-layer router
# ---------------------------------------------------------------------------


@dataclass
class HybridLayerPlan:
    """Resolved per-layer routing plan for a hybrid model.

    Attributes:
        layer_kinds: Ordered list of :class:`LayerKind`, one per model layer.
    """

    layer_kinds: List[LayerKind]

    def __post_init__(self) -> None:
        if not self.layer_kinds:
            raise ValueError("HybridLayerPlan requires at least one layer kind")


class HybridRouter:
    """Route each layer of a hybrid model to its correct sequence mixer.

    Attention layers are delegated to a caller-supplied attention callable
    (the transformer/vanilla path chosen by :mod:`attention_backend`); SSM
    layers run through :class:`SSMScanKernel`.  This is the per-layer routing
    a Jamba-style stack needs — the router owns *dispatch*, the sub-kernels own
    *computation*.

    Args:
        plan: The resolved :class:`HybridLayerPlan`.
        attention_fn: Callable ``(hidden) -> hidden`` for attention layers.
        ssm_kernel: Kernel used for SSM layers; a default :class:`SSMScanKernel`
            is created when omitted.
    """

    def __init__(
        self,
        plan: HybridLayerPlan,
        attention_fn: Callable[[Any], Any],
        ssm_kernel: SSMScanKernel | None = None,
    ) -> None:
        self._plan = plan
        self._attention_fn = attention_fn
        self._ssm = ssm_kernel or SSMScanKernel()

    def kind_for_layer(self, index: int) -> LayerKind:
        """Return the :class:`LayerKind` routing decision for *index*."""
        return self._plan.layer_kinds[index]

    def dispatch_layer(self, index: int, hidden: Any, ssm_params: dict[str, Any] | None = None) -> Any:
        """Run layer *index* through its routed kernel and return the output.

        Args:
            index: Zero-based layer index into the plan.
            hidden: Hidden-state tensor for the layer.
            ssm_params: Required for SSM layers — dict with keys
                ``a``, ``b``, ``c``, ``delta`` for :meth:`SSMScanKernel.forward`.
        """
        if self.kind_for_layer(index) is LayerKind.ATTENTION:
            return self._attention_fn(hidden)
        if ssm_params is None:
            raise ValueError(f"SSM layer {index} requires ssm_params (a, b, c, delta)")
        return self._ssm.forward(hidden, **ssm_params)


__all__ = [
    "HybridLayerPlan",
    "HybridRouter",
    "LayerKind",
    "LinearAttentionConfig",
    "LinearAttentionKernel",
    "SSMConfig",
    "SSMScanKernel",
    "elu_feature_map",
]
