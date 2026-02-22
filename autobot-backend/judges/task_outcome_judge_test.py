# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for TaskOutcomeJudge (Issue #930)
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from judges.task_outcome_judge import (
    MAX_OUTCOMES_PER_TYPE,
    REDIS_OUTCOMES_KEY,
    TaskOutcomeJudge,
    TaskOutcomeRecord,
)


@pytest.fixture
def judge():
    return TaskOutcomeJudge(llm_interface=MagicMock())


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.lpush = AsyncMock()
    redis.ltrim = AsyncMock()
    redis.expire = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    redis.delete = AsyncMock()
    return redis


class TestTaskOutcomeRecord:
    def test_defaults(self):
        record = TaskOutcomeRecord(
            task_type="code_gen",
            goal="write a function",
            output_summary="def f(): pass",
            strategy_used="default",
            score=0.8,
            rationale="Good output",
        )
        assert record.task_type == "code_gen"
        assert record.score == 0.8
        assert record.timestamp  # auto-populated

    def test_serializable_to_json(self):
        record = TaskOutcomeRecord(
            task_type="test",
            goal="goal",
            output_summary="out",
            strategy_used="s",
            score=0.5,
            rationale="r",
        )
        data = json.dumps(record.__dict__)
        restored = TaskOutcomeRecord(**json.loads(data))
        assert restored.score == 0.5


class TestTaskOutcomeJudge:
    @pytest.mark.asyncio
    async def test_get_outcomes_empty(self, judge, mock_redis):
        judge._redis_client = mock_redis
        mock_redis.lrange.return_value = []
        outcomes = await judge.get_outcomes("unknown_type")
        assert outcomes == []

    @pytest.mark.asyncio
    async def test_get_outcomes_returns_records(self, judge, mock_redis):
        judge._redis_client = mock_redis
        record = TaskOutcomeRecord(
            task_type="t",
            goal="g",
            output_summary="o",
            strategy_used="s",
            score=0.7,
            rationale="r",
            timestamp="2025-01-01T00:00:00",
        )
        mock_redis.lrange.return_value = [json.dumps(record.__dict__).encode()]
        outcomes = await judge.get_outcomes("t")
        assert len(outcomes) == 1
        assert outcomes[0].score == 0.7

    @pytest.mark.asyncio
    async def test_clear_outcomes(self, judge, mock_redis):
        judge._redis_client = mock_redis
        await judge.clear_outcomes("mytype")
        mock_redis.delete.assert_awaited_once_with(
            REDIS_OUTCOMES_KEY.format(task_type="mytype")
        )

    @pytest.mark.asyncio
    async def test_persist_outcome_trims_list(self, judge, mock_redis):
        judge._redis_client = mock_redis
        from judges import JudgmentConfidence, JudgmentResult

        result = JudgmentResult(
            subject_id="x",
            judge_type="task_outcome",
            timestamp=datetime.utcnow(),
            overall_score=0.75,
            recommendation="APPROVE",
            confidence=JudgmentConfidence.MEDIUM,
            criterion_scores=[],
            reasoning="ok",
            alternatives_considered=[],
            improvement_suggestions=[],
            context_used={},
            processing_time_ms=10.0,
            llm_model_used="test",
        )
        await judge._persist_outcome("t", "goal", "output", "strategy", result)
        mock_redis.ltrim.assert_awaited_once_with(
            REDIS_OUTCOMES_KEY.format(task_type="t"), 0, MAX_OUTCOMES_PER_TYPE - 1
        )

    @pytest.mark.asyncio
    async def test_persist_outcome_redis_failure_does_not_raise(self, judge):
        judge._redis_client = AsyncMock()
        judge._redis_client.lpush = AsyncMock(side_effect=Exception("Redis down"))
        from judges import JudgmentConfidence, JudgmentResult

        result = JudgmentResult(
            subject_id="x",
            judge_type="task_outcome",
            timestamp=datetime.utcnow(),
            overall_score=0.5,
            recommendation="CONDITIONAL",
            confidence=JudgmentConfidence.LOW,
            criterion_scores=[],
            reasoning="ok",
            alternatives_considered=[],
            improvement_suggestions=[],
            context_used={},
            processing_time_ms=5.0,
            llm_model_used="test",
        )
        # Should not raise
        await judge._persist_outcome("t", "g", "o", "s", result)

    def test_prepare_judgment_prompt_contains_goal(self):
        judge = TaskOutcomeJudge()
        import asyncio

        prompt = asyncio.get_event_loop().run_until_complete(
            judge._prepare_judgment_prompt(
                subject={"goal": "my goal", "output": "my output"},
                criteria=[],
                context={"task_type": "test", "goal": "my goal", "strategy_used": "s"},
            )
        )
        assert "my goal" in prompt
        assert "ACCURACY" in prompt
        assert "COMPLETENESS" in prompt
        assert "EFFICIENCY" in prompt
