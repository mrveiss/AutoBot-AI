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

from agents.task_pattern_learner import LearnedStrategy, TaskPatternLearner


@pytest.fixture
def learner():
    return TaskPatternLearner(llm_interface=None)


@pytest.fixture
def sample_outcomes():
    return [
        {
            "task_type": "t",
            "strategy_used": "direct",
            "score": 0.8,
            "rationale": "good",
        },
        {"task_type": "t", "strategy_used": "direct", "score": 0.4, "rationale": "ok"},
        {"task_type": "t", "strategy_used": "step", "score": 0.9, "rationale": "great"},
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
        learner._redis = mock_redis

        result = await learner.learn_from_outcomes("t", sample_outcomes, tenant_id="org1")
        assert result is not None
        assert result.best_approach == "use step-by-step"
        assert result.confidence == 0.8
        mock_redis.set.assert_awaited_once()
        # GH#11071: persisted under the tenant-scoped key
        assert mock_redis.set.await_args.args[0] == "task:patterns:org1:t"

    @pytest.mark.asyncio
    async def test_learn_from_outcomes_fallback_on_llm_error(self, learner, sample_outcomes):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=Exception("LLM down"))
        learner._llm = mock_llm

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        learner._redis = mock_redis

        result = await learner.learn_from_outcomes("t", sample_outcomes, tenant_id="org1")
        # Fallback creates strategy from best outcome
        assert result is not None
        assert result.task_type == "t"
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
        result = await learner.get_learned_strategy("t", tenant_id="org1")
        assert result is not None
        assert result.best_approach == "direct"
        assert result.avg_score == 0.75
        # GH#11071: read from the tenant-scoped key
        assert mock_redis.get.await_args.args[0] == "task:patterns:org1:t"

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
        await learner.get_learned_strategy("t", tenant_id="orgA")
        await learner.get_learned_strategy("t", tenant_id="orgB")
        assert seen_keys == ["task:patterns:orgA:t", "task:patterns:orgB:t"]

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
            ("Code-Gen", "code_gen"),
            ("  DATA ANALYSIS ", "data_analysis"),
            ("code_gen", "code_gen"),
        ],
    )
    def test_normalize_task_type(self, learner, raw, expected):
        assert learner.normalize_task_type(raw) == expected

    @pytest.mark.asyncio
    async def test_clear_strategy_normalizes_task_type(self, learner):
        mock_redis = AsyncMock()
        learner._redis = mock_redis
        await learner.clear_strategy("Code-Gen", tenant_id="org1")
        mock_redis.delete.assert_awaited_once_with("task:patterns:org1:code_gen")

    def test_build_synthesis_prompt_includes_task_type(self, learner, sample_outcomes):
        best = sample_outcomes[2]
        prompt = learner._build_synthesis_prompt("code_gen", sample_outcomes, best)
        assert "code_gen" in prompt
        assert str(len(sample_outcomes)) in prompt

    def test_fallback_strategy_uses_best_approach(self, learner, sample_outcomes):
        best = sample_outcomes[2]  # score 0.9, strategy "step"
        result = learner._fallback_strategy("t", sample_outcomes, best)
        assert result.best_approach == "step"
        assert result.sample_size == len(sample_outcomes)
        assert result.confidence == 0.3
