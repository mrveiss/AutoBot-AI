# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for TaskPatternLearner (Issue #930)
"""

import json
from unittest.mock import AsyncMock

import pytest

from agents.task_pattern_learner import (
    OTHER_TASK_TYPE,
    LearnedStrategy,
    TaskPatternLearner,
    normalize_task_type,
)


@pytest.fixture
def learner():
    return TaskPatternLearner(llm_interface=None)


@pytest.fixture
def sample_outcomes():
    return [
        {
            "task_type": "code_generation",
            "strategy_used": "direct",
            "score": 0.8,
            "rationale": "good",
            "timestamp": "2025-01-01T00:00:00",
        },
        {
            "task_type": "code_generation",
            "strategy_used": "direct",
            "score": 0.4,
            "rationale": "ok",
            "timestamp": "2025-01-01T00:01:00",
        },
        {
            "task_type": "code_generation",
            "strategy_used": "step",
            "score": 0.9,
            "rationale": "great",
            "timestamp": "2025-01-01T00:02:00",
        },
    ]


class TestLearnedStrategy:
    def test_defaults(self):
        s = LearnedStrategy(
            task_type="t",
            best_approach="direct",
            best_prompt_template="do {goal}",
            avg_score=0.7,
            sample_size=5,
            confidence=0.8,
        )
        assert s.failure_patterns == []
        assert s.timestamp


class TestTaskPatternLearner:
    @pytest.mark.asyncio
    async def test_learn_from_outcomes_not_enough_data(self, learner):
        result = await learner.learn_from_outcomes("t", [{"score": 0.5}], tenant_id="org1")
        assert result is None

    @pytest.mark.asyncio
    async def test_learn_from_outcomes_triggers_synthesis(self, learner, sample_outcomes):
        mock_llm = AsyncMock()
        # The learner calls ``llm.chat(...)`` (not chat_completion).
        mock_llm.chat = AsyncMock(
            return_value=json.dumps(
                {
                    "best_approach": "use step-by-step",
                    "best_prompt_template": "Step by step: {goal}",
                    "failure_patterns": ["too broad"],
                    "confidence": 0.8,
                }
            )
        )
        learner._llm = mock_llm

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.scan = AsyncMock(return_value=(0, []))
        learner._redis = mock_redis

        result = await learner.learn_from_outcomes("code_generation", sample_outcomes, tenant_id="org1")
        assert result is not None
        assert result.best_approach == "use step-by-step"
        assert result.confidence == 0.8
        # GH#11534: provenance is stamped for rollback/audit
        assert result.tenant_id == "org1"
        assert result.source_outcome_ids == [
            "2025-01-01T00:00:00",
            "2025-01-01T00:01:00",
            "2025-01-01T00:02:00",
        ]
        mock_redis.set.assert_awaited_once()
        # GH#11071: persisted under the tenant-scoped key
        assert mock_redis.set.await_args.args[0] == "task:patterns:org1:code_generation"

    @pytest.mark.asyncio
    async def test_learn_from_outcomes_fallback_on_llm_error(self, learner, sample_outcomes):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=Exception("LLM down"))
        learner._llm = mock_llm

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.scan = AsyncMock(return_value=(0, []))
        learner._redis = mock_redis

        result = await learner.learn_from_outcomes("code_generation", sample_outcomes, tenant_id="org1")
        # Fallback creates strategy from best outcome
        assert result is not None
        assert result.task_type == "code_generation"
        assert result.confidence == 0.3  # fallback confidence

    @pytest.mark.asyncio
    async def test_learn_from_outcomes_fails_closed_without_tenant(self, learner, sample_outcomes):
        """GH#11071: an empty tenant_id skips learning entirely (no Redis write)."""
        mock_redis = AsyncMock()
        learner._redis = mock_redis
        result = await learner.learn_from_outcomes("t", sample_outcomes, tenant_id="")
        assert result is None
        mock_redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_learned_strategy_returns_none_when_missing(self, learner):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        learner._redis = mock_redis
        result = await learner.get_learned_strategy("missing_type", tenant_id="org1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_learned_strategy_deserializes(self, learner):
        strategy = LearnedStrategy(
            task_type="t",
            best_approach="direct",
            best_prompt_template="do {goal}",
            avg_score=0.75,
            sample_size=3,
            confidence=0.8,
        )
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(strategy.__dict__).encode())
        learner._redis = mock_redis
        result = await learner.get_learned_strategy("code_generation", tenant_id="org1")
        assert result is not None
        assert result.best_approach == "direct"
        assert result.avg_score == 0.75
        # GH#11071: read from the tenant-scoped key
        assert mock_redis.get.await_args.args[0] == "task:patterns:org1:code_generation"

    @pytest.mark.asyncio
    async def test_get_learned_strategy_fails_closed_without_tenant(self, learner):
        """GH#11071: no tenant → no Redis read, returns None (can't see a shared bucket)."""
        mock_redis = AsyncMock()
        learner._redis = mock_redis
        result = await learner.get_learned_strategy("t", tenant_id="")
        assert result is None
        mock_redis.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_learned_strategy_isolated_per_tenant(self, learner):
        """GH#11071: org B reads its own key, never org A's."""
        seen_keys = []

        async def _get(key):
            seen_keys.append(key)
            return None

        mock_redis = AsyncMock()
        mock_redis.get = _get
        learner._redis = mock_redis
        await learner.get_learned_strategy("code_generation", tenant_id="orgA")
        await learner.get_learned_strategy("code_generation", tenant_id="orgB")
        assert seen_keys == ["task:patterns:orgA:code_generation", "task:patterns:orgB:code_generation"]

    @pytest.mark.asyncio
    async def test_clear_strategy(self, learner):
        mock_redis = AsyncMock()
        learner._redis = mock_redis
        await learner.clear_strategy("mytype", tenant_id="org1")
        mock_redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_all_task_types(self, learner):
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(
            return_value=(
                0,
                [b"task:outcomes:org1:code_gen", b"task:outcomes:org1:analysis"],
            )
        )
        learner._redis = mock_redis
        types = await learner.get_all_task_types(tenant_id="org1")
        assert "code_gen" in types
        assert "analysis" in types
        # GH#11071: scan is scoped to the tenant prefix
        assert mock_redis.scan.await_args.kwargs["match"] == "task:outcomes:org1:*"

    @pytest.mark.parametrize(
        "raw, expected",
        [
            # Known AgentType values — format-canonicalised, preserved.
            ("Code-Generation", "code_generation"),
            ("  DATA ANALYSIS ", "data_analysis"),
            ("code_generation", "code_generation"),
            ("Research", "research"),
            # Known ExecutionStrategy value.
            ("sequential", "sequential"),
            # Known explicit write-path literals.
            ("planning", "planning"),
            ("chat_turn", "chat_turn"),
            ("llc_heartbeat", "llc_heartbeat"),
            # GH#11534: unknown/free-form types bucket to the single "other" key.
            ("code_gen", OTHER_TASK_TYPE),
            ("some_random_free_form", OTHER_TASK_TYPE),
            ("", OTHER_TASK_TYPE),
        ],
    )
    def test_normalize_task_type(self, learner, raw, expected):
        assert learner.normalize_task_type(raw) == expected

    def test_normalize_learner_and_judge_agree(self):
        """GH#11534: judge and learner MUST derive the same key for any input.

        The judge routes through the same module-level ``normalize_task_type`` that
        ``TaskPatternLearner.normalize_task_type`` delegates to, so a learned
        strategy and its outcomes always land under matching task_type keys.
        """
        for raw in ["Code-Generation", "code_gen", "planning", "", "WeIrD Type"]:
            assert TaskPatternLearner.normalize_task_type(raw) == normalize_task_type(raw)

    @pytest.mark.asyncio
    async def test_clear_strategy_normalizes_task_type(self, learner):
        mock_redis = AsyncMock()
        learner._redis = mock_redis
        await learner.clear_strategy("Code-Generation", tenant_id="org1")
        mock_redis.delete.assert_awaited_once_with("task:patterns:org1:code_generation")

    @pytest.mark.asyncio
    async def test_persist_strategy_versions_and_archives(self, learner):
        """GH#11534: overwriting archives the prior revision and bumps version."""
        prior = LearnedStrategy(
            task_type="code_generation",
            best_approach="old",
            best_prompt_template="old {goal}",
            avg_score=0.5,
            sample_size=3,
            confidence=0.6,
            version=1,
        )
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(prior.__dict__))
        mock_redis.scan = AsyncMock(return_value=(0, []))
        learner._redis = mock_redis

        new = LearnedStrategy(
            task_type="code_generation",
            best_approach="new",
            best_prompt_template="new {goal}",
            avg_score=0.9,
            sample_size=3,
            confidence=0.9,
        )
        await learner._persist_strategy("code_generation", new, tenant_id="org1")
        # Prior revision archived to the bounded history list.
        mock_redis.lpush.assert_awaited_once()
        assert mock_redis.lpush.await_args.args[0] == "task:patterns:org1:code_generation:history"
        # New revision version incremented past the prior one.
        assert new.version == 2

    @pytest.mark.asyncio
    async def test_rollback_strategy_restores_previous(self, learner):
        """GH#11534: rollback pops the archived revision and restores it as current."""
        prior = LearnedStrategy(
            task_type="code_generation",
            best_approach="good-old",
            best_prompt_template="old {goal}",
            avg_score=0.7,
            sample_size=3,
            confidence=0.75,
            version=1,
        )
        mock_redis = AsyncMock()
        mock_redis.lpop = AsyncMock(return_value=json.dumps(prior.__dict__))
        mock_redis.set = AsyncMock()
        learner._redis = mock_redis

        restored = await learner.rollback_strategy("code_generation", tenant_id="org1")
        assert restored is not None
        assert restored.best_approach == "good-old"
        mock_redis.lpop.assert_awaited_once_with("task:patterns:org1:code_generation:history")
        # Restored revision written back as current under the tenant-scoped key.
        assert mock_redis.set.await_args.args[0] == "task:patterns:org1:code_generation"

    @pytest.mark.asyncio
    async def test_rollback_strategy_no_history_returns_none(self, learner):
        """GH#11534: nothing to roll back to → None, no write."""
        mock_redis = AsyncMock()
        mock_redis.lpop = AsyncMock(return_value=None)
        learner._redis = mock_redis
        result = await learner.rollback_strategy("code_generation", tenant_id="org1")
        assert result is None
        mock_redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rollback_strategy_fails_closed_without_tenant(self, learner):
        """GH#11071/#11534: no tenant → no Redis op, returns None."""
        mock_redis = AsyncMock()
        learner._redis = mock_redis
        result = await learner.rollback_strategy("code_generation", tenant_id="")
        assert result is None
        mock_redis.lpop.assert_not_awaited()

    def test_build_synthesis_prompt_includes_task_type(self, learner, sample_outcomes):
        best = sample_outcomes[2]
        prompt = learner._build_synthesis_prompt("code_generation", sample_outcomes, best)
        assert "code_generation" in prompt
        assert str(len(sample_outcomes)) in prompt

    def test_fallback_strategy_uses_best_approach(self, learner, sample_outcomes):
        best = sample_outcomes[2]  # score 0.9, strategy "step"
        result = learner._fallback_strategy("code_generation", sample_outcomes, best)
        assert result.best_approach == "step"
        assert result.sample_size == len(sample_outcomes)
        assert result.confidence == 0.3


class TestKeyCap:
    """GH#11534: per-tenant task_type key cap (backstop beyond the allowlist)."""

    @pytest.mark.asyncio
    async def test_new_key_diverted_to_other_when_cap_reached(self, monkeypatch):
        import agents.task_pattern_learner as mod

        monkeypatch.setattr(mod, "MAX_TASK_TYPE_KEYS_PER_TENANT", 2)
        existing = [b"task:outcomes:org1:research", b"task:outcomes:org1:planning"]
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, existing))
        # A brand-new type at the cap is diverted into the shared "other" bucket.
        result = await mod.enforce_key_cap(mock_redis, "task:outcomes:org1:", "code_generation")
        assert result == OTHER_TASK_TYPE

    @pytest.mark.asyncio
    async def test_existing_key_allowed_even_at_cap(self, monkeypatch):
        import agents.task_pattern_learner as mod

        monkeypatch.setattr(mod, "MAX_TASK_TYPE_KEYS_PER_TENANT", 2)
        existing = [b"task:outcomes:org1:research", b"task:outcomes:org1:planning"]
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, existing))
        # An already-present type keeps writing to its own key.
        result = await mod.enforce_key_cap(mock_redis, "task:outcomes:org1:", "research")
        assert result == "research"

    @pytest.mark.asyncio
    async def test_history_subkeys_do_not_count(self, monkeypatch):
        import agents.task_pattern_learner as mod

        monkeypatch.setattr(mod, "MAX_TASK_TYPE_KEYS_PER_TENANT", 2)
        # One real key + one history sub-key → only 1 counts, so a new key is allowed.
        existing = [b"task:patterns:org1:research", b"task:patterns:org1:research:history"]
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, existing))
        result = await mod.enforce_key_cap(mock_redis, "task:patterns:org1:", "planning")
        assert result == "planning"

    @pytest.mark.asyncio
    async def test_cap_fails_open_on_redis_error(self, monkeypatch):
        import agents.task_pattern_learner as mod

        monkeypatch.setattr(mod, "MAX_TASK_TYPE_KEYS_PER_TENANT", 0)
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(side_effect=Exception("redis down"))
        # Cap must never drop data — a scan failure returns the type unchanged.
        result = await mod.enforce_key_cap(mock_redis, "task:outcomes:org1:", "research")
        assert result == "research"
