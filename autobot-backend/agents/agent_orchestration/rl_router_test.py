# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for RLRouter and its integration into AgentRouter (Issue #2092).

All tests are pure in-memory; Redis is fully mocked.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from .rl_router import (
    _CONFIDENCE_BASE,
    _CONFIDENCE_SCALE,
    _EPSILON_MIN,
    _EPSILON_START,
    RLRouter,
)
from .routing import AgentRouter
from .types import AgentType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock(store: dict) -> AsyncMock:
    """Return a Redis-like async mock backed by *store* dict."""
    redis = AsyncMock()

    async def _hget(key, field):
        return store.get((key, field))

    async def _hset(key, field, value):
        store[(key, field)] = value.encode() if isinstance(value, str) else value

    async def _hgetall(key):
        return {k[1].encode(): v for k, v in store.items() if k[0] == key}

    async def _get(key):
        return store.get(key)

    async def _set(key, value):
        store[key] = value.encode() if isinstance(value, str) else value

    async def _lpush(key, value):
        store.setdefault(key, [])
        store[key].insert(0, value.encode() if isinstance(value, str) else value)

    async def _ltrim(key, start, end):
        if key in store and isinstance(store[key], list):
            store[key] = store[key][start : end + 1]

    async def _lrange(key, start, end):
        items = store.get(key, [])
        return items[start : end + 1] if isinstance(items, list) else []

    redis.hget = _hget
    redis.hset = _hset
    redis.hgetall = _hgetall
    redis.get = _get
    redis.set = _set
    redis.lpush = _lpush
    redis.ltrim = _ltrim
    redis.lrange = _lrange
    return redis


async def _make_router(store: dict | None = None) -> RLRouter:
    """Return an RLRouter with Redis replaced by the in-memory mock."""
    if store is None:
        store = {}
    router = RLRouter()
    router._redis = _make_redis_mock(store)
    return router


# ---------------------------------------------------------------------------
# State hashing
# ---------------------------------------------------------------------------


class TestStateHashing:
    def test_deterministic(self):
        router = RLRouter()
        key1 = router._hash_state("Write a Python function to sort a list")
        key2 = router._hash_state("Write a Python function to sort a list")
        assert key1 == key2

    def test_different_queries_differ(self):
        router = RLRouter()
        k1 = router._hash_state("Write a Python function")
        k2 = router._hash_state("Translate this to French")
        assert k1 != k2

    def test_domain_keyword_detected(self):
        router = RLRouter()
        key = router._hash_state("generate code for sorting")
        # "code" domain keyword should appear in the key
        assert "code" in key

    def test_length_bucket_short(self):
        router = RLRouter()
        key = router._hash_state("hello")
        assert "short" in key

    def test_length_bucket_long(self):
        router = RLRouter()
        key = router._hash_state(" ".join(["word"] * 35))
        assert "long" in key

    def test_no_domain_falls_back_to_generic(self):
        router = RLRouter()
        key = router._hash_state("xyz qrs abc def")
        assert "generic" in key


# ---------------------------------------------------------------------------
# Epsilon-greedy selection
# ---------------------------------------------------------------------------


class TestEpsilonGreedy:
    @pytest.mark.asyncio
    async def test_explore_when_epsilon_is_one(self):
        """With epsilon=1.0 the router always picks randomly."""
        store = {}
        router = await _make_router(store)
        # Force epsilon to 1.0
        store[_KEY("rl:router:epsilon")] = b"1.0"
        agents = ["chat", "code_generation", "research"]
        selections = set()
        for _ in range(50):
            agent_id, _, _ = await router.select_agent("hello world", agents)
            selections.add(agent_id)
        # With 50 draws over 3 agents, all three should appear
        assert len(selections) > 1

    @pytest.mark.asyncio
    async def test_exploit_when_epsilon_is_zero(self):
        """With epsilon=0.0 the router always picks the highest-Q agent."""
        store = {}
        router = await _make_router(store)
        state_key = router._hash_state("write code")
        store[_KEY("rl:router:epsilon")] = b"0.0"
        # Plant Q-values: code_generation is best
        qtable_key = f"rl:router:qtable:{state_key}"
        store[(qtable_key, "chat")] = b"0.3"
        store[(qtable_key, "code_generation")] = b"0.9"
        store[(qtable_key, "research")] = b"0.1"

        agents = ["chat", "code_generation", "research"]
        for _ in range(10):
            agent_id, _, _ = await router.select_agent("write code", agents)
            assert agent_id == "code_generation"

    @pytest.mark.asyncio
    async def test_epsilon_decays_over_steps(self):
        """Epsilon decreases with each call to select_agent."""
        store = {}
        router = await _make_router(store)
        agents = ["chat"]
        await router.select_agent("test query", agents)
        eps_after_one = float((store.get("rl:router:epsilon") or store.get(b"rl:router:epsilon", b"1.0")))
        assert eps_after_one < _EPSILON_START

    @pytest.mark.asyncio
    async def test_epsilon_floors_at_minimum(self):
        """Epsilon never drops below _EPSILON_MIN regardless of step count."""
        store = {}
        router = await _make_router(store)
        store[_KEY("rl:router:epsilon")] = str(_EPSILON_MIN).encode()
        agents = ["chat"]
        # Run many steps
        for _ in range(20):
            await router.select_agent("test", agents)
        final_eps_raw = store.get("rl:router:epsilon") or store.get(b"rl:router:epsilon")
        if final_eps_raw:
            final_eps = float(final_eps_raw)
            assert final_eps >= _EPSILON_MIN


# ---------------------------------------------------------------------------
# Q-table update
# ---------------------------------------------------------------------------


class TestQTableUpdate:
    @pytest.mark.asyncio
    async def test_reward_increases_q_value(self):
        store = {}
        router = await _make_router(store)
        state_key = "test:state"
        await router.record_outcome(state_key, "chat", reward=1.0)
        q = await router._q_get(state_key, "chat")
        assert q > 0.5  # Started at 0.5 optimistic init; reward=1 pushes it up

    @pytest.mark.asyncio
    async def test_zero_reward_decreases_q_value(self):
        store = {}
        router = await _make_router(store)
        state_key = "test:state"
        await router.record_outcome(state_key, "chat", reward=0.0)
        q = await router._q_get(state_key, "chat")
        assert q < 0.5

    @pytest.mark.asyncio
    async def test_q_value_clamped_to_unit_interval(self):
        store = {}
        router = await _make_router(store)
        state_key = "clamp:state"
        # Drive Q to 1.0 via repeated perfect rewards
        for _ in range(100):
            await router._q_update(state_key, "chat", reward=1.0)
        q = await router._q_get(state_key, "chat")
        assert q <= 1.0

        # Drive Q to 0.0 via repeated zero rewards
        for _ in range(100):
            await router._q_update(state_key, "chat", reward=0.0)
        q = await router._q_get(state_key, "chat")
        assert q >= 0.0

    @pytest.mark.asyncio
    async def test_q_default_is_optimistic(self):
        store = {}
        router = await _make_router(store)
        q = await router._q_get("unknown:state", "unknown_agent")
        assert q == 0.5


# ---------------------------------------------------------------------------
# Confidence mapping
# ---------------------------------------------------------------------------


class TestConfidenceMapping:
    @pytest.mark.asyncio
    async def test_confidence_at_q_zero(self):
        store = {}
        router = await _make_router(store)
        state_key = "conf:state"
        store[(f"rl:router:qtable:{state_key}", "chat")] = b"0.0"
        confidence = await router._agent_confidence(state_key, "chat")
        assert abs(confidence - _CONFIDENCE_BASE) < 1e-6

    @pytest.mark.asyncio
    async def test_confidence_at_q_one(self):
        store = {}
        router = await _make_router(store)
        state_key = "conf:state"
        store[(f"rl:router:qtable:{state_key}", "chat")] = b"1.0"
        confidence = await router._agent_confidence(state_key, "chat")
        assert abs(confidence - (_CONFIDENCE_BASE + _CONFIDENCE_SCALE)) < 1e-6

    @pytest.mark.asyncio
    async def test_confidence_between_0_6_and_1_0(self):
        store = {}
        router = await _make_router(store)
        state_key = "conf:state"
        for q in [0.0, 0.25, 0.5, 0.75, 1.0]:
            store[(f"rl:router:qtable:{state_key}", "chat")] = str(q).encode()
            c = await router._agent_confidence(state_key, "chat")
            assert 0.6 <= c <= 1.0


# ---------------------------------------------------------------------------
# AgentRouter integration
# ---------------------------------------------------------------------------


class TestAgentRouterRLIntegration:
    def _make_agent_router(self, rl_router=None):
        caps = {AgentType.CHAT: MagicMock(), AgentType.CODE_GENERATION: MagicMock()}
        llm = AsyncMock()
        router = AgentRouter(agent_capabilities=caps, llm_interface=llm)
        router._rl_router = rl_router
        return router

    @pytest.mark.asyncio
    async def test_rl_result_used_when_confidence_above_threshold(self):
        """RL route is returned when confidence > 0.6 and quick-match fails."""
        rl_mock = AsyncMock()
        rl_mock.select_agent = AsyncMock(return_value=("chat", 0.75, "state:abc"))

        router = self._make_agent_router(rl_mock)
        # Use a query that won't trigger quick_route confidence > 0.8
        result = await router.determine_routing("something ambiguous here please help me decide")
        assert result.get("source") == "rl"
        assert result["confidence"] == 0.75

    @pytest.mark.asyncio
    async def test_rl_skipped_when_confidence_too_low(self):
        """LLM fallback is used when RL confidence is <= 0.6."""
        rl_mock = AsyncMock()
        rl_mock.select_agent = AsyncMock(return_value=("chat", 0.55, "state:abc"))

        llm_response = json.dumps(
            {
                "strategy": "single_agent",
                "primary_agent": "chat",
                "confidence": 0.7,
                "reasoning": "LLM chose chat",
            }
        )
        router = self._make_agent_router(rl_mock)
        router.llm_interface.chat_completion = AsyncMock(return_value={"content": llm_response})

        result = await router.determine_routing("something ambiguous here please help me decide")
        # Should NOT be 'rl' source — LLM was used
        assert result.get("source") != "rl"

    @pytest.mark.asyncio
    async def test_kill_switch_disables_rl(self):
        """Setting rl_routing_enabled=False bypasses RL and goes to LLM."""
        rl_mock = AsyncMock()
        rl_mock.select_agent = AsyncMock(return_value=("chat", 0.9, "state:abc"))

        llm_response = json.dumps(
            {
                "strategy": "single_agent",
                "primary_agent": "chat",
                "confidence": 0.7,
                "reasoning": "LLM chose chat",
            }
        )
        router = self._make_agent_router(rl_mock)
        router.rl_routing_enabled = False
        router.llm_interface.chat_completion = AsyncMock(return_value={"content": llm_response})

        result = await router.determine_routing("something ambiguous here please help me decide")
        assert result.get("source") != "rl"

    @pytest.mark.asyncio
    async def test_rl_error_falls_through_to_llm(self):
        """An exception in RL routing falls through gracefully to LLM."""
        rl_mock = AsyncMock()
        rl_mock.select_agent = AsyncMock(side_effect=RuntimeError("redis unavailable"))

        llm_response = json.dumps(
            {
                "strategy": "single_agent",
                "primary_agent": "chat",
                "confidence": 0.7,
                "reasoning": "LLM fallback",
            }
        )
        router = self._make_agent_router(rl_mock)
        router.llm_interface.chat_completion = AsyncMock(return_value={"content": llm_response})

        # Should not raise — falls back to LLM silently
        result = await router.determine_routing("something ambiguous here please help me decide")
        assert result is not None
        assert result.get("source") != "rl"

    @pytest.mark.asyncio
    async def test_high_confidence_pattern_match_bypasses_rl(self):
        """Pattern match with confidence > 0.8 should skip RL entirely."""
        rl_mock = AsyncMock()
        router = self._make_agent_router(rl_mock)
        # "hello" triggers GREETING_PATTERNS → confidence 0.9
        result = await router.determine_routing("hello")
        assert result["confidence"] > 0.8
        rl_mock.select_agent.assert_not_called()


# ---------------------------------------------------------------------------
# Helpers (key normalisation for dict-backed mock)
# ---------------------------------------------------------------------------


def _KEY(k: str) -> str:  # noqa: N802 — matches Redis key naming convention
    return k
