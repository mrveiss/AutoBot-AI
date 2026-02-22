# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
        result = await learner.learn_from_outcomes("t", [{"score": 0.5}])
        assert result is None

    @pytest.mark.asyncio
    async def test_learn_from_outcomes_triggers_synthesis(
        self, learner, sample_outcomes
    ):
        mock_llm = AsyncMock()
        mock_llm.chat_completion_async = AsyncMock(
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

        result = await learner.learn_from_outcomes("t", sample_outcomes)
        assert result is not None
        assert result.best_approach == "use step-by-step"
        assert result.confidence == 0.8
        mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_learn_from_outcomes_fallback_on_llm_error(
        self, learner, sample_outcomes
    ):
        mock_llm = AsyncMock()
        mock_llm.chat_completion_async = AsyncMock(side_effect=Exception("LLM down"))
        learner._llm = mock_llm

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        learner._redis = mock_redis

        result = await learner.learn_from_outcomes("t", sample_outcomes)
        # Fallback creates strategy from best outcome
        assert result is not None
        assert result.task_type == "t"
        assert result.confidence == 0.3  # fallback confidence

    @pytest.mark.asyncio
    async def test_get_learned_strategy_returns_none_when_missing(self, learner):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        learner._redis = mock_redis
        result = await learner.get_learned_strategy("missing_type")
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
        result = await learner.get_learned_strategy("t")
        assert result is not None
        assert result.best_approach == "direct"
        assert result.avg_score == 0.75

    @pytest.mark.asyncio
    async def test_clear_strategy(self, learner):
        mock_redis = AsyncMock()
        learner._redis = mock_redis
        await learner.clear_strategy("mytype")
        mock_redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_all_task_types(self, learner):
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(
            return_value=(
                0,
                [b"task:outcomes:code_gen", b"task:outcomes:analysis"],
            )
        )
        learner._redis = mock_redis
        types = await learner.get_all_task_types()
        assert "code_gen" in types
        assert "analysis" in types

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
