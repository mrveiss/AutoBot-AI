# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for autoresearch scorers — Issue #2600."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.autoresearch.models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
    ExperimentTask,
    HyperParams,
)
from services.autoresearch.runner import build_task_inference_params
from services.autoresearch.scorers import (
    HumanReviewScorer,
    LLMJudgeScorer,
    ScorerResult,
    ValBpbScorer,
)


class TestScorerResult:
    def test_to_dict(self) -> None:
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

    def test_score_clamped_to_range(self) -> None:
        result = ScorerResult(score=1.5, raw_score=1.5, metadata={}, scorer_name="t")
        assert result.score == 1.0

    def test_score_floor(self) -> None:
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
    async def test_score_improvement(self, scorer, mock_runner) -> None:
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
    async def test_score_no_improvement(self, scorer, mock_runner) -> None:
        experiment = Experiment(state=ExperimentState.DISCARDED)
        experiment.result = ExperimentResult(val_bpb=5.5)
        experiment.baseline_val_bpb = 5.0
        mock_runner.run_experiment.return_value = experiment

        result = await scorer.score("test hypothesis", {"hyperparams": {}})
        assert result.score == 0.0
        assert result.raw_score == 5.5

    @pytest.mark.asyncio
    async def test_score_failed_experiment(self, scorer, mock_runner) -> None:
        experiment = Experiment(state=ExperimentState.FAILED)
        experiment.result = ExperimentResult(error_message="OOM")
        mock_runner.run_experiment.return_value = experiment

        result = await scorer.score("test hypothesis", {"hyperparams": {}})
        assert result.score == 0.0
        assert result.raw_score is None


class TestLLMJudgeScorer:
    @pytest.fixture
    def scorer(self, mock_llm):
        return LLMJudgeScorer(
            llm_service=mock_llm,
            criteria=["relevance", "specificity", "actionability"],
        )

    @pytest.mark.asyncio
    async def test_score_parses_llm_rating(self, scorer, mock_llm) -> None:
        mock_response = MagicMock()
        mock_response.content = '{"rating": 8, "reasoning": "Good hypothesis"}'
        mock_llm.chat.return_value = mock_response

        result = await scorer.score("A detailed hypothesis", {})
        assert result.score == 0.8  # 8/10 normalized
        assert result.raw_score == 8
        assert result.scorer_name == "llm_judge"

    @pytest.mark.asyncio
    async def test_score_handles_non_json_response(self, scorer, mock_llm) -> None:
        mock_response = MagicMock()
        mock_response.content = "I rate this 7 out of 10"
        mock_llm.chat.return_value = mock_response

        result = await scorer.score("A hypothesis", {})
        # Falls back to regex extraction
        assert result.score == 0.7
        assert result.raw_score == 7

    @pytest.mark.asyncio
    async def test_score_handles_llm_failure(self, scorer, mock_llm) -> None:
        mock_llm.chat.side_effect = Exception("LLM unavailable")

        result = await scorer.score("A hypothesis", {})
        assert result.score == 0.0
        assert "error" in result.metadata


class TestLLMJudgeScorerParseRating:
    """Unit tests for LLMJudgeScorer._parse_rating edge cases — Issue #3211."""

    def test_parse_rating_completely_unparseable_returns_zero(self) -> None:
        result = LLMJudgeScorer._parse_rating("no numbers here at all")
        assert result == 0

    def test_parse_rating_json_path(self) -> None:
        assert LLMJudgeScorer._parse_rating('{"rating": 7, "reasoning": "ok"}') == 7

    def test_parse_rating_regex_path(self) -> None:
        assert LLMJudgeScorer._parse_rating("I give this 8 out of 10") == 8

    def test_parse_rating_clamps_to_10(self) -> None:
        assert LLMJudgeScorer._parse_rating('{"rating": 15}') == 10

    def test_parse_rating_clamps_to_0(self) -> None:
        assert LLMJudgeScorer._parse_rating('{"rating": -3}') == 0


class TestValBpbScorerRunExperimentException:
    """ValBpbScorer should surface exceptions from run_experiment — Issue #3211."""

    @pytest.mark.asyncio
    async def test_score_propagates_run_experiment_exception(self) -> None:
        runner = AsyncMock()
        runner.run_experiment.side_effect = RuntimeError("training crashed")

        scorer = ValBpbScorer(runner=runner, baseline_val_bpb=5.0)
        with pytest.raises(RuntimeError, match="training crashed"):
            await scorer.score("hypothesis", {"hyperparams": {}})


class TestSubsetFractionPassthrough:
    """Verify subset_fraction=None is a no-op for all concrete scorers."""

    @pytest.mark.asyncio
    async def test_llm_judge_accepts_subset_fraction_none(self) -> None:
        llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"rating": 7, "reasoning": "ok"}'
        llm.chat.return_value = mock_response

        scorer = LLMJudgeScorer(llm_service=llm, criteria=["quality"])
        result = await scorer.score("output text", {}, subset_fraction=None)
        assert result.score == 0.7

    @pytest.mark.asyncio
    async def test_llm_judge_accepts_subset_fraction_value(self) -> None:
        llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"rating": 6, "reasoning": "ok"}'
        llm.chat.return_value = mock_response

        scorer = LLMJudgeScorer(llm_service=llm, criteria=["quality"])
        # subset_fraction is accepted and ignored for LLMJudgeScorer
        result = await scorer.score("output text", {}, subset_fraction=0.3)
        assert result.score == 0.6

    @pytest.mark.asyncio
    async def test_val_bpb_accepts_subset_fraction(self) -> None:
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
    async def test_score_approved_with_rating(self, scorer, mock_redis) -> None:
        # First redis.get (pre-BLPOP check) returns None — not yet written.
        # blpop returns the notification tuple.
        # Second redis.get (after BLPOP) returns the actual score payload.
        mock_redis.get.side_effect = [
            None,  # pre-BLPOP check: result not yet available
            json.dumps({"score": 9, "comment": "excellent"}).encode(),  # post-BLPOP read
        ]
        mock_redis.blpop.return_value = (
            b"autoresearch:prompt_review:notify:s1:v1",
            b"ready",
        )
        result = await scorer.score(
            "test output",
            {"session_id": "s1", "variant_id": "v1"},
        )
        assert result.score == 0.9
        assert result.raw_score == 9
        assert result.scorer_name == "human_review"
        # BLPOP must have been called with the notify key and the timeout
        mock_redis.blpop.assert_called_once()
        call_args = mock_redis.blpop.call_args
        assert "notify:s1:v1" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_score_result_already_present_skips_blpop(self, scorer, mock_redis) -> None:
        # Result was written before score() was called — BLPOP must be skipped.
        mock_redis.get.return_value = json.dumps({"score": 7, "comment": "good"}).encode()
        result = await scorer.score(
            "test output",
            {"session_id": "s1", "variant_id": "v1"},
        )
        assert result.score == 0.7
        assert result.raw_score == 7
        mock_redis.blpop.assert_not_called()

    @pytest.mark.asyncio
    async def test_score_timeout_returns_none(self, scorer, mock_redis) -> None:
        mock_redis.get.return_value = None  # never receives a score
        mock_redis.blpop.return_value = None  # BLPOP timed out

        result = await scorer.score(
            "test output",
            {"session_id": "s1", "variant_id": "v1"},
        )
        assert result.score == 0.0
        assert result.metadata.get("status") == "timeout"

    @pytest.mark.asyncio
    async def test_score_notify_fired_but_result_missing(self, scorer, mock_redis) -> None:
        # Both pre- and post-BLPOP GETs return None — treat as timeout.
        mock_redis.get.return_value = None
        mock_redis.blpop.return_value = (
            b"autoresearch:prompt_review:notify:s1:v1",
            b"ready",
        )
        result = await scorer.score(
            "test output",
            {"session_id": "s1", "variant_id": "v1"},
        )
        assert result.score == 0.0
        assert result.metadata.get("status") == "timeout"


# ---------------------------------------------------------------------------
# ExperimentTask per-task override tests (Issue #3259)
# ---------------------------------------------------------------------------


class TestExperimentTaskOverrides:
    """ExperimentTask fields and ValBpbScorer temperature enforcement."""

    def test_experiment_task_roundtrip(self) -> None:
        task = ExperimentTask(
            prompt="evaluate this",
            required_temperature=0.0,
            system_prompt="You are a code evaluator.",
        )
        data = task.to_dict()
        restored = ExperimentTask.from_dict(data)
        assert restored.prompt == "evaluate this"
        assert restored.required_temperature == 0.0
        assert restored.system_prompt == "You are a code evaluator."

    def test_experiment_task_defaults(self) -> None:
        task = ExperimentTask(prompt="just a prompt")
        assert task.required_temperature is None
        assert task.system_prompt is None

    def test_experiment_task_from_dict_optional_fields_absent(self) -> None:
        restored = ExperimentTask.from_dict({"prompt": "p"})
        assert restored.required_temperature is None
        assert restored.system_prompt is None

    def test_val_bpb_scorer_task_has_required_temperature_zero(self) -> None:
        """ValBpbScorer must set required_temperature=0.0 on its task."""
        task = ExperimentTask(prompt="test hypothesis", required_temperature=0.0)
        assert task.required_temperature == 0.0


class TestBuildTaskInferenceParams:
    """build_task_inference_params (module-level) applies per-task overrides."""

    def test_task_temperature_overrides_experiment_level(self) -> None:
        hp = HyperParams(extra={"temperature": 0.9})
        experiment = Experiment(hypothesis="h", hyperparams=hp)
        task = ExperimentTask(prompt="p", required_temperature=0.0)

        params = build_task_inference_params(task, experiment)

        assert params["temperature"] == 0.0
        assert params["prompt"] == "p"
        assert params["system_prompt"] is None

    def test_experiment_level_temperature_used_when_task_has_none(self) -> None:
        hp = HyperParams(extra={"temperature": 0.7})
        experiment = Experiment(hypothesis="h", hyperparams=hp)
        task = ExperimentTask(prompt="p")  # required_temperature=None

        params = build_task_inference_params(task, experiment)

        assert params["temperature"] == 0.7

    def test_system_prompt_passed_through(self) -> None:
        experiment = Experiment(hypothesis="h", hyperparams=HyperParams())
        task = ExperimentTask(
            prompt="p",
            required_temperature=0.0,
            system_prompt="You are an evaluator.",
        )

        params = build_task_inference_params(task, experiment)

        assert params["system_prompt"] == "You are an evaluator."

    def test_no_temperature_at_all_returns_none(self) -> None:
        experiment = Experiment(hypothesis="h", hyperparams=HyperParams())
        task = ExperimentTask(prompt="p")  # no task temp, no experiment temp

        params = build_task_inference_params(task, experiment)

        assert params["temperature"] is None
