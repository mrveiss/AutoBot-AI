# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for TaskOutcomeJudge (Issue #930)
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.datetime_utils import datetime_now
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
    # GH#11534: persist normalizes then caps distinct keys via a SCAN sweep.
    redis.scan = AsyncMock(return_value=(0, []))
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
        outcomes = await judge.get_outcomes("unknown_type", tenant_id="org1")
        assert outcomes == []

    @pytest.mark.asyncio
    async def test_get_outcomes_fails_closed_without_tenant(self, judge, mock_redis):
        """GH#11071: no tenant → no Redis read, returns [] (can't see a shared bucket)."""
        judge._redis_client = mock_redis
        outcomes = await judge.get_outcomes("t", tenant_id="")
        assert outcomes == []
        mock_redis.lrange.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_outcomes_returns_records(self, judge, mock_redis):
        judge._redis_client = mock_redis
        record = TaskOutcomeRecord(
            task_type="code_generation",
            goal="g",
            output_summary="o",
            strategy_used="s",
            score=0.7,
            rationale="r",
            timestamp="2025-01-01T00:00:00",
        )
        mock_redis.lrange.return_value = [json.dumps(record.__dict__).encode()]
        outcomes = await judge.get_outcomes("code_generation", tenant_id="org1")
        assert len(outcomes) == 1
        assert outcomes[0].score == 0.7
        # GH#11071: read from the tenant-scoped key
        assert mock_redis.lrange.await_args.args[0] == "task:outcomes:org1:code_generation"

    @pytest.mark.asyncio
    async def test_clear_outcomes(self, judge, mock_redis):
        judge._redis_client = mock_redis
        await judge.clear_outcomes("code_generation", tenant_id="org1")
        mock_redis.delete.assert_awaited_once_with(
            REDIS_OUTCOMES_KEY.format(tenant_id="org1", task_type="code_generation")
        )

    @pytest.mark.asyncio
    async def test_clear_outcomes_buckets_unknown_to_other(self, judge, mock_redis):
        """GH#11534: an unknown free-form type resolves to the shared 'other' key."""
        judge._redis_client = mock_redis
        await judge.clear_outcomes("some_free_form_type", tenant_id="org1")
        mock_redis.delete.assert_awaited_once_with(REDIS_OUTCOMES_KEY.format(tenant_id="org1", task_type="other"))

    @pytest.mark.asyncio
    async def test_persist_outcome_trims_list(self, judge, mock_redis):
        judge._redis_client = mock_redis
        from judges import JudgmentConfidence, JudgmentResult

        result = JudgmentResult(
            subject_id="x",
            judge_type="task_outcome",
            timestamp=datetime_now(),
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
        await judge._persist_outcome("code_generation", "goal", "output", "strategy", result, tenant_id="org1")
        mock_redis.ltrim.assert_awaited_once_with(
            REDIS_OUTCOMES_KEY.format(tenant_id="org1", task_type="code_generation"), 0, MAX_OUTCOMES_PER_TYPE - 1
        )

    @pytest.mark.asyncio
    async def test_persist_outcome_normalizes_unknown_to_other(self, judge, mock_redis):
        """GH#11534: a free-form task_type is bucketed to 'other' before persisting,
        keeping the judge's key in agreement with TaskPatternLearner."""
        judge._redis_client = mock_redis
        from judges import JudgmentConfidence, JudgmentResult

        result = JudgmentResult(
            subject_id="x",
            judge_type="task_outcome",
            timestamp=datetime_now(),
            overall_score=0.6,
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
        await judge._persist_outcome("totally-random type", "g", "o", "s", result, tenant_id="org1")
        assert mock_redis.lpush.await_args.args[0] == REDIS_OUTCOMES_KEY.format(tenant_id="org1", task_type="other")

    @pytest.mark.asyncio
    async def test_persist_outcome_redis_failure_does_not_raise(self, judge):
        judge._redis_client = AsyncMock()
        judge._redis_client.lpush = AsyncMock(side_effect=Exception("Redis down"))
        from judges import JudgmentConfidence, JudgmentResult

        result = JudgmentResult(
            subject_id="x",
            judge_type="task_outcome",
            timestamp=datetime_now(),
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
        await judge._persist_outcome("t", "g", "o", "s", result, tenant_id="org1")

    @pytest.mark.asyncio
    async def test_judge_and_learner_agree_on_persisted_key(self, judge, mock_redis):
        """GH#11534: the judge persists an outcome under exactly the key the
        TaskPatternLearner would read/write for the same task_type input."""
        from agents.task_pattern_learner import normalize_task_type

        judge._redis_client = mock_redis
        from judges import JudgmentConfidence, JudgmentResult

        result = JudgmentResult(
            subject_id="x",
            judge_type="task_outcome",
            timestamp=datetime_now(),
            overall_score=0.6,
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
        raw_type = "Code-Generation"
        await judge._persist_outcome(raw_type, "g", "o", "s", result, tenant_id="org1")
        expected = REDIS_OUTCOMES_KEY.format(tenant_id="org1", task_type=normalize_task_type(raw_type))
        assert mock_redis.lpush.await_args.args[0] == expected

    @pytest.mark.asyncio
    async def test_prepare_judgment_prompt_contains_goal(self):
        judge = TaskOutcomeJudge()

        prompt = await judge._prepare_judgment_prompt(
            subject={"goal": "my goal", "output": "my output"},
            criteria=[],
            context={"task_type": "test", "goal": "my goal", "strategy_used": "s"},
        )
        assert "my goal" in prompt
        assert "ACCURACY" in prompt
        assert "COMPLETENESS" in prompt
        assert "EFFICIENCY" in prompt
