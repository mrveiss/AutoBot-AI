# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for autoresearch scorers — Issue #2600."""

from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.autoresearch.models import Experiment, ExperimentResult, ExperimentState
from services.autoresearch.scorers import (
    HumanReviewScorer,
    LLMJudgeScorer,
    ScorerResult,
    ValBpbScorer,
)


class TestScorerResult:
    def test_to_dict(self):
        result = ScorerResult(
            score=0.85,
            raw_score=4.2,
            metadata={"model": "test"},
            scorer_name="test_scorer",
        )
        d = result.to_dict()
        assert d["score"] == 0.85
        assert d["raw_score"] == 4.2
        assert d["metadata"] == {"model": "test"}
        assert d["scorer_name"] == "test_scorer"

    def test_score_clamped_to_range(self):
        result = ScorerResult(score=1.5, raw_score=1.5, metadata={}, scorer_name="t")
        assert result.score == 1.0

    def test_score_floor(self):
        result = ScorerResult(score=-0.5, raw_score=-0.5, metadata={}, scorer_name="t")
        assert result.score == 0.0


class TestValBpbScorer:
    @pytest.fixture
    def mock_runner(self):
        runner = AsyncMock()
        return runner

    @pytest.fixture
    def scorer(self, mock_runner):
        return ValBpbScorer(runner=mock_runner, baseline_val_bpb=5.0)

    @pytest.mark.asyncio
    async def test_score_improvement(self, scorer, mock_runner):
        experiment = Experiment(state=ExperimentState.KEPT)
        experiment.result = ExperimentResult(val_bpb=4.5)
        experiment.baseline_val_bpb = 5.0
        mock_runner.run_experiment.return_value = experiment

        result = await scorer.score(
            "test hypothesis",
            {"hyperparams": {}},
        )
        assert result.score > 0.0
        assert result.raw_score == 4.5
        assert result.scorer_name == "val_bpb"

    @pytest.mark.asyncio
    async def test_score_no_improvement(self, scorer, mock_runner):
        experiment = Experiment(state=ExperimentState.DISCARDED)
        experiment.result = ExperimentResult(val_bpb=5.5)
        experiment.baseline_val_bpb = 5.0
        mock_runner.run_experiment.return_value = experiment

        result = await scorer.score("test hypothesis", {"hyperparams": {}})
        assert result.score == 0.0
        assert result.raw_score == 5.5

    @pytest.mark.asyncio
    async def test_score_failed_experiment(self, scorer, mock_runner):
        experiment = Experiment(state=ExperimentState.FAILED)
        experiment.result = ExperimentResult(error_message="OOM")
        mock_runner.run_experiment.return_value = experiment

        result = await scorer.score("test hypothesis", {"hyperparams": {}})
        assert result.score == 0.0
        assert result.raw_score is None


class TestLLMJudgeScorer:
    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        return llm

    @pytest.fixture
    def scorer(self, mock_llm):
        return LLMJudgeScorer(
            llm_service=mock_llm,
            criteria=["relevance", "specificity", "actionability"],
        )

    @pytest.mark.asyncio
    async def test_score_parses_llm_rating(self, scorer, mock_llm):
        mock_response = MagicMock()
        mock_response.content = '{"rating": 8, "reasoning": "Good hypothesis"}'
        mock_llm.chat.return_value = mock_response

        result = await scorer.score("A detailed hypothesis", {})
        assert result.score == 0.8  # 8/10 normalized
        assert result.raw_score == 8
        assert result.scorer_name == "llm_judge"

    @pytest.mark.asyncio
    async def test_score_handles_non_json_response(self, scorer, mock_llm):
        mock_response = MagicMock()
        mock_response.content = "I rate this 7 out of 10"
        mock_llm.chat.return_value = mock_response

        result = await scorer.score("A hypothesis", {})
        # Falls back to regex extraction
        assert result.score == 0.7
        assert result.raw_score == 7

    @pytest.mark.asyncio
    async def test_score_handles_llm_failure(self, scorer, mock_llm):
        mock_llm.chat.side_effect = Exception("LLM unavailable")

        result = await scorer.score("A hypothesis", {})
        assert result.score == 0.0
        assert "error" in result.metadata


class TestSubsetFractionPassthrough:
    """Verify subset_fraction=None is a no-op for all concrete scorers."""

    @pytest.mark.asyncio
    async def test_llm_judge_accepts_subset_fraction_none(self):
        llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"rating": 7, "reasoning": "ok"}'
        llm.chat.return_value = mock_response

        scorer = LLMJudgeScorer(llm_service=llm, criteria=["quality"])
        result = await scorer.score("output text", {}, subset_fraction=None)
        assert result.score == 0.7

    @pytest.mark.asyncio
    async def test_llm_judge_accepts_subset_fraction_value(self):
        llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"rating": 6, "reasoning": "ok"}'
        llm.chat.return_value = mock_response

        scorer = LLMJudgeScorer(llm_service=llm, criteria=["quality"])
        # subset_fraction is accepted and ignored for LLMJudgeScorer
        result = await scorer.score("output text", {}, subset_fraction=0.3)
        assert result.score == 0.6

    @pytest.mark.asyncio
    async def test_val_bpb_accepts_subset_fraction(self):
        runner = AsyncMock()
        experiment = MagicMock()
        experiment.result = MagicMock()
        experiment.result.val_bpb = 4.0
        experiment.state = MagicMock()
        experiment.state.value = "kept"
        runner.run_experiment.return_value = experiment

        scorer = ValBpbScorer(runner=runner, baseline_val_bpb=5.0)
        result = await scorer.score("hypothesis", {}, subset_fraction=0.3)
        # full experiment still runs; subset_fraction is logged and ignored
        assert result.score > 0.0


class TestHumanReviewScorer:
    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        return redis

    @pytest.fixture
    def scorer(self, mock_redis):
        s = HumanReviewScorer(poll_interval=0.01, timeout=0.05)
        s._redis = mock_redis
        return s

    @pytest.mark.asyncio
    async def test_score_approved_with_rating(self, scorer, mock_redis):
        # Simulate human submitting a score
        mock_redis.get.side_effect = [
            None,  # first poll: no score yet
            json.dumps({"score": 9, "comment": "excellent"}).encode(),  # second poll
        ]
        result = await scorer.score(
            "test output",
            {"session_id": "s1", "variant_id": "v1"},
        )
        assert result.score == 0.9
        assert result.raw_score == 9
        assert result.scorer_name == "human_review"

    @pytest.mark.asyncio
    async def test_score_timeout_returns_none(self, scorer, mock_redis):
        mock_redis.get.return_value = None  # never receives a score

        result = await scorer.score(
            "test output",
            {"session_id": "s1", "variant_id": "v1"},
        )
        assert result.score == 0.0
        assert result.metadata.get("status") == "timeout"
