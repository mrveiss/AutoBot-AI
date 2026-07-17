# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for routing strategies introduced in issue #6595.

Tests ComplexityRouter, CostRouter, LatencyRouter, and the strategy registry
without hitting Redis or real LLM providers.

Updated for the current scorer contract (issue #11834): GH#9050 (76062f245)
added a "trivial" tier below "simple", and MVA-2022 (452ffd9ae) routes
trivial/simple scores to the complex tier when no lower-tier model is
configured.  Fixture messages are tiered accordingly.
"""

import sys
from unittest.mock import patch

import pytest

from llm_shared.tiered_routing.base_strategy import RoutingStrategy
from llm_shared.tiered_routing.complexity_router import ComplexityRouter
from llm_shared.tiered_routing.cost_router import CostRouter
from llm_shared.tiered_routing.latency_router import LatencyRouter
from llm_shared.tiered_routing.long_context_router import (
    LONG_CONTEXT_PROMPT_THRESHOLD,
    LongContextRouter,
)
from llm_shared.tiered_routing.registry import get_active_router
from llm_shared.tiered_routing.tier_config import TierConfig, TierModels

# NOTE: tier_router is intentionally NOT imported at module level — conftest.py
# stubs llm_shared.tiered_routing.tier_router with a MagicMock (services need a
# mock get_tiered_router).  test_backward_compat_alias real-loads it with
# snapshot/restore.

# Scores 0.0 → "trivial" tier (below trivial_threshold=1.0, GH#9050).
TRIVIAL_MSG = [{"role": "user", "content": "hi"}]

# Scores ~1.9 → "simple" tier (between trivial_threshold and complexity_threshold).
SIMPLE_MSG = [
    {
        "role": "user",
        "content": (
            "Can you compare the pros and cons of using Redis as a cache "
            "for our api? Also mention performance considerations."
        ),
    }
]

# Scores ~8.6 → "complex" tier (code + technical + multistep + question factors;
# the pre-#9050 message only reached ~1.9 under the current factor weights).
COMPLEX_MSG = [
    {
        "role": "user",
        "content": (
            "Design a distributed microservice architecture with authentication, "
            "authorization, encryption, and cache layers backed by Redis and a sql "
            "database. First analyze the trade-offs between optimistic and "
            "pessimistic concurrency control, then implement a Python module for "
            "the replication algorithm:\n"
            "```python\nimport asyncio\n\nasync def replicate_log(entries):\n    ...\n```\n"
            "Step 1: explain how leader election works. Step 2: implement an "
            "error-handling strategy for network partitions. Finally, explain why "
            "the design avoids deadlock and race condition issues, and optimize "
            "the hot path for performance and scalability."
        ),
    }
]


@pytest.fixture
def config():
    return TierConfig(
        enabled=True,
        complexity_threshold=3.0,
        models=TierModels(trivial="tiny-model", simple="cheap-model", complex="capable-model"),
    )


# ─── ComplexityRouter ────────────────────────────────────────────────────────


class TestComplexityRouter:
    def test_trivial_message_selects_trivial_model(self, config):
        # GH#9050: ultra-simple queries route to the trivial tier.
        router = ComplexityRouter(config)
        model, result = router.route(TRIVIAL_MSG)
        assert model == "tiny-model"
        assert result.tier == "trivial"

    def test_trivial_without_trivial_model_falls_back_to_complex(self, config):
        # MVA-2022: with no trivial model configured, sub-simple scores route
        # to the complex tier (not simple) and the tier field is rewritten.
        config.models.trivial = ""
        router = ComplexityRouter(config)
        model, result = router.route(TRIVIAL_MSG)
        assert model == "capable-model"
        assert result.tier == "complex"

    def test_simple_message_selects_simple_model(self, config):
        router = ComplexityRouter(config)
        model, result = router.route(SIMPLE_MSG)
        assert model == "cheap-model"
        assert result.tier == "simple"

    def test_complex_message_selects_complex_model(self, config):
        router = ComplexityRouter(config)
        model, result = router.route(COMPLEX_MSG)
        assert model == "capable-model"
        assert result.tier == "complex"

    def test_disabled_always_returns_complex(self, config):
        config.enabled = False
        router = ComplexityRouter(config)
        model, _ = router.route(SIMPLE_MSG)
        assert model == "capable-model"

    def test_metrics_accumulate(self, config):
        router = ComplexityRouter(config)
        router.route(SIMPLE_MSG)
        router.route(SIMPLE_MSG)
        router.route(COMPLEX_MSG)
        metrics = router.get_metrics()
        assert metrics["total_requests"] == 3

    def test_protocol_compliance(self, config):
        router = ComplexityRouter(config)
        assert isinstance(router, RoutingStrategy)

    def test_backward_compat_alias(self, config):
        # conftest.py replaces llm_shared.tiered_routing.tier_router with a
        # MagicMock stub (services import get_tiered_router).  Real-load the
        # module here with snapshot/restore so we verify the real alias.
        import importlib

        mod_name = "llm_shared.tiered_routing.tier_router"
        parent = sys.modules["llm_shared.tiered_routing"]
        stub = sys.modules.pop(mod_name, None)
        stub_attr = getattr(parent, "tier_router", None)
        try:
            real_tr = importlib.import_module(mod_name)
            assert real_tr.TieredModelRouter is ComplexityRouter
            router = real_tr.get_tiered_router(config, force_new=True)
            assert isinstance(router, ComplexityRouter)
        finally:
            sys.modules.pop(mod_name, None)
            if stub is not None:
                sys.modules[mod_name] = stub
            if stub_attr is not None:
                parent.tier_router = stub_attr


# ─── CostRouter ──────────────────────────────────────────────────────────────


class TestCostRouter:
    def test_prefers_cheaper_model_for_simple_request(self, config):
        with patch(
            "llm_shared.tiered_routing.cost_router.MODEL_PRICING_PER_1M_TOKENS",
            {"cheap-model": {"input": 0.1, "output": 0.4}, "capable-model": {"input": 3.0, "output": 15.0}},
        ):
            router = CostRouter(config)
            model, result = router.route(SIMPLE_MSG)
            assert model == "cheap-model"

    def test_trivial_request_still_eligible_for_cheap_model(self, config):
        # Issue #11834: GH#9050's trivial tier must not push the easiest
        # requests to the expensive complex-only candidate set.
        with patch(
            "llm_shared.tiered_routing.cost_router.MODEL_PRICING_PER_1M_TOKENS",
            {"cheap-model": {"input": 0.1, "output": 0.4}, "capable-model": {"input": 3.0, "output": 15.0}},
        ):
            router = CostRouter(config)
            model, _ = router.route(TRIVIAL_MSG)
            assert model == "cheap-model"

    def test_complex_request_uses_complex_model_regardless_of_cost(self, config):
        with patch(
            "llm_shared.tiered_routing.cost_router.MODEL_PRICING_PER_1M_TOKENS",
            {"cheap-model": {"input": 0.1, "output": 0.4}, "capable-model": {"input": 3.0, "output": 15.0}},
        ):
            router = CostRouter(config)
            model, _ = router.route(COMPLEX_MSG)
            assert model == "capable-model"

    def test_zero_cost_local_models_return_first_candidate(self, config):
        with patch(
            "llm_shared.tiered_routing.cost_router.MODEL_PRICING_PER_1M_TOKENS",
            {},  # local models not in pricing table → 0.0
        ):
            router = CostRouter(config)
            model, _ = router.route(SIMPLE_MSG)
            # falls back to first candidate (simple)
            assert model == "cheap-model"

    def test_metrics_include_cost_savings(self, config):
        with patch(
            "llm_shared.tiered_routing.cost_router.MODEL_PRICING_PER_1M_TOKENS",
            {"cheap-model": {"input": 0.1, "output": 0.4}, "capable-model": {"input": 3.0, "output": 15.0}},
        ):
            router = CostRouter(config)
            router.route(SIMPLE_MSG)
            metrics = router.get_metrics()
            assert metrics["estimated_cost_savings_usd"] >= 0.0

    def test_protocol_compliance(self, config):
        router = CostRouter(config)
        assert isinstance(router, RoutingStrategy)


# ─── LatencyRouter ───────────────────────────────────────────────────────────


class TestLatencyRouter:
    def test_no_p95_data_still_routes(self, config):
        router = LatencyRouter(config)
        model, result = router.route(SIMPLE_MSG)
        assert model in ("cheap-model", "capable-model")

    def test_lower_cached_p95_wins(self, config):
        router = LatencyRouter(config)
        router._p95_cache = {"cheap-model": 200.0, "capable-model": 800.0}
        model, result = router.route(SIMPLE_MSG)
        assert model == "cheap-model"

    def test_higher_latency_on_simple_selects_complex(self, config):
        router = LatencyRouter(config)
        router._p95_cache = {"cheap-model": 2000.0, "capable-model": 300.0}
        model, _ = router.route(SIMPLE_MSG)
        assert model == "capable-model"

    def test_complex_request_only_considers_complex_model(self, config):
        router = LatencyRouter(config)
        router._p95_cache = {"cheap-model": 10.0, "capable-model": 5000.0}
        model, _ = router.route(COMPLEX_MSG)
        # complex tier is the only candidate for complex requests
        assert model == "capable-model"

    def test_metrics_include_p95_cache(self, config):
        router = LatencyRouter(config)
        router._p95_cache = {"cheap-model": 150.0}
        metrics = router.get_metrics()
        assert "p95_cache" in metrics
        assert metrics["p95_cache"]["cheap-model"] == 150.0

    def test_protocol_compliance(self, config):
        router = LatencyRouter(config)
        assert isinstance(router, RoutingStrategy)


# ─── Registry ────────────────────────────────────────────────────────────────


class TestStrategyRegistry:
    def test_default_strategy_is_complexity(self, config):
        with patch.dict("os.environ", {"AUTOBOT_LLM_ROUTING_STRATEGY": ""}):
            router = get_active_router(config, force_new=True)
        assert isinstance(router, ComplexityRouter)

    def test_env_override_selects_cost(self, config):
        with patch.dict("os.environ", {"AUTOBOT_LLM_ROUTING_STRATEGY": "cost"}):
            router = get_active_router(config, force_new=True)
        assert isinstance(router, CostRouter)

    def test_env_override_selects_latency(self, config):
        with patch.dict("os.environ", {"AUTOBOT_LLM_ROUTING_STRATEGY": "latency"}):
            router = get_active_router(config, force_new=True)
        assert isinstance(router, LatencyRouter)

    def test_unknown_strategy_falls_back_to_complexity(self, config):
        with patch.dict("os.environ", {"AUTOBOT_LLM_ROUTING_STRATEGY": "bogus_strategy"}):
            router = get_active_router(config, force_new=True)
        assert isinstance(router, ComplexityRouter)

    def test_env_override_selects_long_context(self, config):
        with patch.dict("os.environ", {"AUTOBOT_LLM_ROUTING_STRATEGY": "long_context"}):
            router = get_active_router(config, force_new=True)
        assert isinstance(router, LongContextRouter)


# ─── LongContextRouter ───────────────────────────────────────────────────────

# Synthetic prompt that exceeds LONG_CONTEXT_PROMPT_THRESHOLD when measured
# by the char/4 estimator (8 192 * 4 = 32 768 chars).
_LONG_PROMPT = "a" * (LONG_CONTEXT_PROMPT_THRESHOLD * 4 + 4)
LONG_MSG = [{"role": "user", "content": _LONG_PROMPT}]

_MAMBA_MODEL = "mamba-large"
_CANDIDATE_REGISTRY = {
    _MAMBA_MODEL: {
        "display_name": _MAMBA_MODEL,
        "architecture_family": "ssm",
        "context_window_tokens": 131_072,
    },
    "_aliases": {},
}


def _router_with_eligible(config, eligible: list) -> LongContextRouter:
    """Create a LongContextRouter with a pre-populated eligible-model cache."""
    router = LongContextRouter(config)
    router._eligible_cache = eligible
    return router


class TestLongContextRouter:
    def test_protocol_compliance(self, config):
        router = LongContextRouter(config)
        assert isinstance(router, RoutingStrategy)

    def test_long_prompt_routes_to_mamba_model(self, config):
        """A >8K-token prompt must reach a registered Mamba model — AC1."""
        router = _router_with_eligible(config, [_MAMBA_MODEL])
        model, result = router.route(LONG_MSG)
        assert model == _MAMBA_MODEL
        assert result.tier == "long_context"

    def test_long_prompt_no_compression_tier(self, config):
        """The tier for a long SSM-routed request must be 'long_context', not compressed."""
        router = _router_with_eligible(config, [_MAMBA_MODEL])
        _, result = router.route(LONG_MSG)
        assert result.tier == "long_context"
        assert result.input_tokens > LONG_CONTEXT_PROMPT_THRESHOLD

    def test_fallback_graceful_when_no_eligible_model(self, config):
        """Must fall back gracefully to simple/complex when no SSM model registered — AC2."""
        router = _router_with_eligible(config, [])
        model, result = router.route(LONG_MSG)
        assert model in (config.models.simple, config.models.complex)
        assert result.tier != "long_context"

    def test_short_prompt_bypasses_long_context_tier(self, config):
        """Prompts under the threshold are not routed to long_context."""
        router = _router_with_eligible(config, [_MAMBA_MODEL])
        model, result = router.route(SIMPLE_MSG)
        assert result.tier != "long_context"
        assert model != _MAMBA_MODEL

    def test_disabled_always_returns_complex(self, config):
        config.enabled = False
        router = LongContextRouter(config)
        model, result = router.route(LONG_MSG)
        assert model == config.models.complex
        assert result.tier == "complex"

    def test_metrics_record_long_context_tier(self, config):
        router = _router_with_eligible(config, [_MAMBA_MODEL])
        router.route(LONG_MSG)
        metrics = router.get_metrics()
        assert metrics["long_context_tier_requests"] == 1
        assert metrics["total_requests"] == 1

    def test_eligible_model_cache_is_populated(self, config):
        """Cache is populated after first route; list_long_context_candidates not re-called."""
        router = _router_with_eligible(config, [_MAMBA_MODEL])
        router.route(LONG_MSG)
        # Cache already set; _get_eligible_models should not call the discovery fn again.
        assert router._eligible_cache == [_MAMBA_MODEL]

    def test_invalidate_cache_clears_eligible_models(self, config):
        router = _router_with_eligible(config, [_MAMBA_MODEL])
        router.route(LONG_MSG)
        router.invalidate_cache()
        assert router._eligible_cache is None

    def test_picks_largest_context_window_model(self, config):
        """First entry in the eligible list is selected (already sorted descending)."""
        router = _router_with_eligible(config, ["mamba-256k", "mamba-64k"])
        model, _ = router.route(LONG_MSG)
        assert model == "mamba-256k"
