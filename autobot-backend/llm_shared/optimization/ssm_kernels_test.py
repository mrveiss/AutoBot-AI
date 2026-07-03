# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for ssm_kernels — numerical correctness of the SSM selective scan,
linear attention (associative vs. direct, causal masking), and hybrid
per-layer routing.

Tensor-math tests require real PyTorch; they are skipped when the conftest
MagicMock torch stub is active (torch not installed).  Routing / plan tests
run without torch.

Issue #10724: real SSM/linear/hybrid kernels replacing NOT_APPLICABLE stubs.
"""

import types

import pytest
import torch

from llm_shared.optimization.ssm_kernels import (
    HybridLayerPlan,
    HybridRouter,
    LayerKind,
    LinearAttentionConfig,
    LinearAttentionKernel,
    SSMConfig,
    SSMScanKernel,
    elu_feature_map,
)

# Detect conftest MagicMock torch stub; skip tensor tests when absent (#5728).
_TORCH_IS_STUB = not isinstance(torch, types.ModuleType)
requires_torch = pytest.mark.skipif(_TORCH_IS_STUB, reason="requires real PyTorch")


# ---------------------------------------------------------------------------
# Naive reference implementations (independent of the kernel under test)
# ---------------------------------------------------------------------------


def _naive_ssm_scan(x, a, b, c, delta, clamp_dt=1e-4):
    """Plain-Python reference for the selective scan (loops, no einsum)."""
    dt = torch.nn.functional.softplus(delta).clamp_min(clamp_dt)  # (B, L, D)
    batch, length, dim = x.shape
    n = a.shape[-1]
    y = torch.zeros(batch, length, dim, dtype=x.dtype)
    for bi in range(batch):
        h = torch.zeros(dim, n, dtype=x.dtype)
        for t in range(length):
            a_bar = torch.exp(dt[bi, t].unsqueeze(-1) * a)  # (D, N)
            b_bar = dt[bi, t].unsqueeze(-1) * b[bi, t].unsqueeze(0)  # (D, N)
            h = a_bar * h + b_bar * x[bi, t].unsqueeze(-1)  # (D, N)
            y[bi, t] = (h * c[bi, t].unsqueeze(0)).sum(dim=-1)  # (D,)
    return y


def _direct_linear_attention(q, k, v, causal, phi, eps=1e-6):
    """Direct O(L²) reference: normalise(φ(Q) φ(K)ᵀ) V."""
    pq, pk = phi(q), phi(k)
    scores = torch.einsum("bhld,bhmd->bhlm", pq, pk)  # (B,H,L,L)
    if causal:
        length = scores.shape[-1]
        mask = torch.tril(torch.ones(length, length, dtype=torch.bool))
        scores = scores.masked_fill(~mask, 0.0)
    denom = scores.sum(dim=-1, keepdim=True).clamp_min(eps)
    weights = scores / denom
    return torch.einsum("bhlm,bhme->bhle", weights, v)


# ---------------------------------------------------------------------------
# SSM selective scan
# ---------------------------------------------------------------------------


@requires_torch
class TestSSMScanKernel:
    """Numerical correctness of the Mamba-style selective scan."""

    @staticmethod
    def _inputs(batch=2, length=5, dim=3, n=4):
        torch.manual_seed(0)
        x = torch.randn(batch, length, dim)
        a = -torch.rand(dim, n)  # negative diagonal state matrix
        b = torch.randn(batch, length, n)
        c = torch.randn(batch, length, n)
        delta = torch.randn(batch, length, dim)
        return x, a, b, c, delta

    def test_matches_naive_reference(self):
        """Kernel output must match a naive loop recurrence within tolerance."""
        x, a, b, c, delta = self._inputs()
        got = SSMScanKernel().forward(x, a, b, c, delta)
        want = _naive_ssm_scan(x, a, b, c, delta)
        assert torch.allclose(got, want, atol=1e-5, rtol=1e-4)

    def test_output_shape(self):
        """Output must be (B, L, D)."""
        x, a, b, c, delta = self._inputs(batch=2, length=6, dim=3, n=4)
        got = SSMScanKernel().forward(x, a, b, c, delta)
        assert tuple(got.shape) == (2, 6, 3)

    def test_zero_input_gives_zero_output(self):
        """With x = 0 and h_0 = 0 the whole scan output is zero."""
        _, a, b, c, delta = self._inputs()
        x = torch.zeros(2, 5, 3)
        got = SSMScanKernel().forward(x, a, b, c, delta)
        assert torch.allclose(got, torch.zeros_like(got), atol=1e-6)

    def test_causality_first_step_independent_of_future(self):
        """y_0 must not change when only later-position inputs change."""
        x, a, b, c, delta = self._inputs(batch=1, length=4, dim=2, n=3)
        kernel = SSMScanKernel()
        y0 = kernel.forward(x, a, b, c, delta)[:, 0]
        x2 = x.clone()
        x2[:, 2:] += 10.0  # perturb only the future
        y0_again = kernel.forward(x2, a, b, c, delta)[:, 0]
        assert torch.allclose(y0, y0_again, atol=1e-6)

    def test_clamp_dt_config_used(self):
        """A large clamp keeps Δ positive and the scan finite."""
        x, a, b, c, delta = self._inputs()
        got = SSMScanKernel(SSMConfig(clamp_dt=0.5)).forward(x, a, b, c, delta)
        assert torch.isfinite(got).all()


# ---------------------------------------------------------------------------
# Linear attention
# ---------------------------------------------------------------------------


@requires_torch
class TestLinearAttentionKernel:
    """Numerical correctness of the feature-map linear attention."""

    @staticmethod
    def _inputs(batch=2, heads=2, length=5, dim=4, dv=3):
        torch.manual_seed(1)
        q = torch.randn(batch, heads, length, dim)
        k = torch.randn(batch, heads, length, dim)
        v = torch.randn(batch, heads, length, dv)
        return q, k, v

    def test_non_causal_matches_direct(self):
        """Associative O(L) form must equal the direct φ(Q)φ(K)ᵀV computation."""
        q, k, v = self._inputs()
        got = LinearAttentionKernel(LinearAttentionConfig(causal=False)).forward(q, k, v)
        want = _direct_linear_attention(q, k, v, causal=False, phi=elu_feature_map)
        assert torch.allclose(got, want, atol=1e-5, rtol=1e-4)

    def test_causal_matches_direct_masked(self):
        """Causal cumsum form must equal the direct lower-triangular-masked form."""
        q, k, v = self._inputs()
        got = LinearAttentionKernel(LinearAttentionConfig(causal=True)).forward(q, k, v)
        want = _direct_linear_attention(q, k, v, causal=True, phi=elu_feature_map)
        assert torch.allclose(got, want, atol=1e-5, rtol=1e-4)

    def test_causal_first_position_ignores_future(self):
        """Causal output at t=0 must be invariant to future keys/values."""
        q, k, v = self._inputs(batch=1, heads=1, length=4, dim=3, dv=2)
        kernel = LinearAttentionKernel(LinearAttentionConfig(causal=True))
        base = kernel.forward(q, k, v)[:, :, 0]
        k2, v2 = k.clone(), v.clone()
        k2[:, :, 1:] += 5.0
        v2[:, :, 1:] += 5.0
        perturbed = kernel.forward(q, k2, v2)[:, :, 0]
        assert torch.allclose(base, perturbed, atol=1e-5)

    def test_output_shape(self):
        """Output must be (B, H, L, D_v)."""
        q, k, v = self._inputs(batch=2, heads=3, length=5, dim=4, dv=6)
        got = LinearAttentionKernel().forward(q, k, v)
        assert tuple(got.shape) == (2, 3, 5, 6)

    def test_elu_feature_map_is_positive(self):
        """φ = elu(x)+1 must be strictly positive for all inputs."""
        x = torch.tensor([-100.0, -1.0, 0.0, 1.0, 100.0])
        assert (elu_feature_map(x) > 0).all()


# ---------------------------------------------------------------------------
# Hybrid per-layer routing
# ---------------------------------------------------------------------------


class TestHybridLayerPlan:
    """Plan validation — runs without torch."""

    def test_empty_plan_rejected(self):
        """An empty layer plan must raise ValueError."""
        with pytest.raises(ValueError):
            HybridLayerPlan(layer_kinds=[])

    def test_plan_preserves_order(self):
        """Layer kinds are stored in order."""
        kinds = [LayerKind.ATTENTION, LayerKind.SSM, LayerKind.ATTENTION]
        plan = HybridLayerPlan(layer_kinds=kinds)
        assert plan.layer_kinds == kinds


class TestHybridRouterDispatch:
    """Routing decisions — attention layers vs SSM layers (no torch needed)."""

    def _plan(self):
        return HybridLayerPlan(
            layer_kinds=[LayerKind.ATTENTION, LayerKind.SSM, LayerKind.ATTENTION]
        )

    def test_attention_layer_calls_attention_fn(self):
        """Attention layers must route through the caller-supplied attention_fn."""
        calls = []

        def attn(hidden):
            calls.append(hidden)
            return "ATTN_OUT"

        router = HybridRouter(self._plan(), attention_fn=attn)
        out = router.dispatch_layer(0, hidden="H0")
        assert out == "ATTN_OUT"
        assert calls == ["H0"]

    def test_ssm_layer_calls_ssm_kernel(self):
        """SSM layers must route to the SSM kernel, not the attention_fn."""

        class _SpyKernel:
            def __init__(self):
                self.called = False

            def forward(self, hidden, **params):
                self.called = True
                return "SSM_OUT"

        spy = _SpyKernel()

        def attn(_hidden):
            raise AssertionError("attention_fn must not be called for SSM layers")

        router = HybridRouter(self._plan(), attention_fn=attn, ssm_kernel=spy)
        out = router.dispatch_layer(
            1, hidden="H1", ssm_params={"a": 1, "b": 2, "c": 3, "delta": 4}
        )
        assert out == "SSM_OUT"
        assert spy.called

    def test_kind_for_layer_reports_route(self):
        """kind_for_layer must reflect the plan per index."""
        router = HybridRouter(self._plan(), attention_fn=lambda h: h)
        assert router.kind_for_layer(0) is LayerKind.ATTENTION
        assert router.kind_for_layer(1) is LayerKind.SSM
        assert router.kind_for_layer(2) is LayerKind.ATTENTION

    def test_ssm_layer_without_params_raises(self):
        """Dispatching an SSM layer without ssm_params must raise ValueError."""
        router = HybridRouter(self._plan(), attention_fn=lambda h: h)
        with pytest.raises(ValueError):
            router.dispatch_layer(1, hidden="H1")

    @requires_torch
    def test_ssm_layer_end_to_end_with_real_kernel(self):
        """A real SSM layer produces a finite (B, L, D) tensor via the default kernel."""
        torch.manual_seed(2)
        batch, length, dim, n = 1, 4, 2, 3
        hidden = torch.randn(batch, length, dim)
        params = {
            "a": -torch.rand(dim, n),
            "b": torch.randn(batch, length, n),
            "c": torch.randn(batch, length, n),
            "delta": torch.randn(batch, length, dim),
        }
        router = HybridRouter(
            HybridLayerPlan(layer_kinds=[LayerKind.SSM]),
            attention_fn=lambda h: h,
        )
        out = router.dispatch_layer(0, hidden=hidden, ssm_params=params)
        assert tuple(out.shape) == (batch, length, dim)
        assert torch.isfinite(out).all()
