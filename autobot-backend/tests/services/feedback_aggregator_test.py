# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the closed feedback→behavior loop aggregator. Issue #10545.

Covers the three acceptance criteria:
  1. Repeated rejection in a tenant demonstrably shifts the next choice.
  2. The adjustment is explainable (surfaced for the trajectory).
  3. Signals are tenant-isolated — org-A feedback never affects org-B.
Plus: bounded influence, evidence floor, and the routing consumption hook.
"""

import pytest

from services.feedback_aggregator import (
    _MAX_BIAS,
    FeedbackAggregator,
    PreferenceSignal,
)


class FakeRedis:
    """Minimal stateful in-memory async Redis for HASH ops used by the aggregator."""

    def __init__(self) -> None:
        self.store: dict = {}

    async def hgetall(self, key):
        return dict(self.store.get(key, {}))

    async def hset(self, key, mapping=None):
        self.store.setdefault(key, {}).update(mapping or {})
        return 1

    async def expire(self, key, ttl):
        return True


def _agg() -> tuple[FeedbackAggregator, FakeRedis]:
    redis = FakeRedis()
    return FeedbackAggregator(redis=redis), redis


async def _reject_n(agg, behavior, n, **scope):
    for _ in range(n):
        await agg.record_signal("rejected", behavior, **scope)


# ---------------------------------------------------------------------------
# Signal storage + tenant isolation of the key layout
# ---------------------------------------------------------------------------


def test_key_is_org_isolated():
    key_a = FeedbackAggregator._key("orgA", "u1", "code-fix", "regex_approach")
    key_b = FeedbackAggregator._key("orgB", "u1", "code-fix", "regex_approach")
    assert key_a != key_b
    assert key_a.startswith("pref:signal:orgA:")
    assert key_b.startswith("pref:signal:orgB:")


@pytest.mark.asyncio
async def test_record_signal_accumulates_aversion():
    agg, _ = _agg()
    await _reject_n(agg, "regex_approach", 5, task_class="code-fix", org_id="orgA", user_id="u1")
    signal = await agg._best_signal("regex_approach", "code-fix", "u1", "orgA")
    assert signal is not None
    assert signal.reject_count == 5
    assert signal.aversion > 0.4


# ---------------------------------------------------------------------------
# AC1 — repeated rejection shifts the next choice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeated_rejection_produces_negative_bias():
    agg, _ = _agg()
    scope = {"task_class": "code-fix", "org_id": "orgA", "user_id": "u1"}
    # Below the evidence floor: no bias yet.
    await _reject_n(agg, "regex_approach", 2, **scope)
    assert await agg.get_bias("regex_approach", **scope) is None
    # After more rejections a bounded negative bias appears.
    await _reject_n(agg, "regex_approach", 4, **scope)
    bias = await agg.get_bias("regex_approach", **scope)
    assert bias is not None
    assert bias.bias < 0


@pytest.mark.asyncio
async def test_routing_hook_shifts_confidence_down():
    """The AgentRouter hook lowers confidence for a rejected agent (shift)."""
    from agents.agent_orchestration.routing import AgentRouter

    agg, _redis = _agg()
    scope = {"task_class": "code-fix", "org_id": "orgA", "user_id": "u1"}
    await _reject_n(agg, "research", 6, **scope)

    router = AgentRouter.__new__(AgentRouter)  # skip heavy __init__
    decision = {"primary_agent": "research", "confidence": 0.7, "reasoning": "base"}
    context = {**scope}

    # Patch the singleton to our stateful aggregator for the lookup.
    import services.feedback_aggregator as fa

    original = fa.get_feedback_aggregator
    fa.get_feedback_aggregator = lambda: agg
    try:
        biased = await router._apply_preference_bias(decision, context)
    finally:
        fa.get_feedback_aggregator = original

    assert biased["confidence"] < 0.7  # demonstrable shift away from 'research'
    assert "preference_bias" in biased


# ---------------------------------------------------------------------------
# AC2 — explainable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bias_is_explainable():
    agg, _ = _agg()
    scope = {"task_class": "code-fix", "org_id": "orgA", "user_id": "u1"}
    await _reject_n(agg, "regex_approach", 6, reason="prefers AST parsing", **scope)
    bias = await agg.get_bias("regex_approach", **scope)
    assert bias is not None
    entry = bias.to_trajectory_entry()
    assert entry["kind"] == "preference_bias"
    assert "regex_approach" in bias.explanation
    assert "rejected/edited" in bias.explanation
    assert "prefers AST parsing" in bias.explanation  # human reason surfaced
    assert entry["evidence_events"] == 6


# ---------------------------------------------------------------------------
# AC3 — tenant isolation: org-A feedback never affects org-B
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_cross_org_leakage():
    agg, _ = _agg()
    await _reject_n(agg, "regex_approach", 8, task_class="code-fix", org_id="orgA", user_id="u1")

    # Same behavior/task-class/user but a DIFFERENT org must see no signal.
    leaked = await agg.get_bias("regex_approach", task_class="code-fix", org_id="orgB", user_id="u1")
    assert leaked is None

    # Org A still sees its own signal.
    own = await agg.get_bias("regex_approach", task_class="code-fix", org_id="orgA", user_id="u1")
    assert own is not None


@pytest.mark.asyncio
async def test_org_wide_fallback_within_same_org_only():
    agg, _ = _agg()
    # Org-wide (global user) rejections in org A.
    await _reject_n(agg, "regex_approach", 6, task_class="code-fix", org_id="orgA")
    # A different user in the SAME org inherits the org-wide preference.
    inherited = await agg.get_bias("regex_approach", task_class="code-fix", org_id="orgA", user_id="u_new")
    assert inherited is not None
    # A user in org B does not.
    assert await agg.get_bias("regex_approach", task_class="code-fix", org_id="orgB", user_id="u_new") is None


# ---------------------------------------------------------------------------
# Bounded influence + acceptance dampening
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bias_is_bounded():
    agg, _ = _agg()
    scope = {"task_class": "code-fix", "org_id": "orgA", "user_id": "u1"}
    await _reject_n(agg, "regex_approach", 50, **scope)  # extreme aversion
    bias = await agg.get_bias("regex_approach", **scope)
    assert bias is not None
    assert abs(bias.bias) <= _MAX_BIAS  # never exceeds the cap


@pytest.mark.asyncio
async def test_acceptance_lowers_aversion_below_floor():
    agg, _ = _agg()
    scope = {"task_class": "code-fix", "org_id": "orgA", "user_id": "u1"}
    await _reject_n(agg, "regex_approach", 4, **scope)
    for _ in range(15):
        await agg.record_signal("accepted", "regex_approach", **scope)
    # Sustained acceptance dampens the EMA back under the noise floor → no bias.
    assert await agg.get_bias("regex_approach", **scope) is None


def test_signal_roundtrip_serialisation():
    sig = PreferenceSignal(
        org_id="orgA",
        user_id="u1",
        task_class="code-fix",
        behavior="x",
        reject_count=3,
        aversion=0.5,
        last_reason="why",
    )
    restored = PreferenceSignal.from_redis_mapping(sig.to_redis_mapping())
    assert restored.reject_count == 3
    assert restored.aversion == 0.5
    assert restored.last_reason == "why"
