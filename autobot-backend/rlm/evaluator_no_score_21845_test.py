# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed evaluation has no score, serializes that absence the same way everywhere, and is counted (#21845)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from prometheus_client import CollectorRegistry

from autobot_shared.monitoring.metrics import quality_gates
from autobot_shared.monitoring.metrics.quality_gates import QualityGateMetricsRecorder
from chat_workflow.reflection_gate import evaluate_with_one_retry
from eval.report import RegressionReport, TrajectoryOutcome
from rlm import types as rlm_types
from rlm.evaluator import ResponseQualityEvaluator
from rlm.types import ReflectionResult, ReflectionVerdict, RLMConfig


def _failed(iteration: int = 1) -> ReflectionResult:
    return ReflectionResult(ReflectionVerdict.INDETERMINATE, None, "boom", "hint", iteration, evaluator_failed=True)


def test_the_failed_verdict_serializes_the_absence_as_a_null_score_with_the_key_present():
    data = _failed().to_dict()
    assert "quality_score" in data and data["quality_score"] is None
    assert data["evaluator_failed"] is True


def test_the_shared_assessment_has_no_score_and_does_not_pass_a_threshold():
    assessment = _failed().assessment(threshold=0.7)
    assert assessment.score is None and assessment.passed is False
    assert _failed().assessment().passed is None  # no threshold: no outcome


def test_a_real_score_still_serializes_as_a_number():
    result = ReflectionResult(ReflectionVerdict.ACCEPT, 0.9)
    assert result.to_dict()["quality_score"] == 0.9 and "evaluator_failed" not in result.to_dict()


def _outcome(candidate):
    return TrajectoryOutcome(
        "t",
        "qa",
        baseline_score=0.9,
        candidate_score=candidate,
        tools_ok=True,
        status_ok=True,
        score_indeterminate=True,
    )


def test_the_eval_report_carries_the_absence_as_null_and_na_never_as_a_zero():
    report = RegressionReport(outcomes=[_outcome(None)])
    assert report.to_dict()["trajectories"][0]["candidate_score"] is None
    assert "candidate=n/a" in report.render_markdown()
    assert report.to_dict()["trajectories"][0]["verdict"] == "unmeasured"


def test_an_outcome_with_no_score_is_unmeasured_even_if_not_flagged():
    outcome = TrajectoryOutcome("t", "qa", 0.9, None, tools_ok=True, status_ok=True)
    assert outcome.classify() == "unmeasured"


def test_the_evaluator_timeout_is_the_registered_env_backed_constant():
    from autobot_shared.env_registry import env

    assert RLMConfig().timeout_ms == rlm_types.RLM_EVAL_TIMEOUT_MS
    assert env("AUTOBOT_RLM_EVAL_TIMEOUT_MS") == 10000 or rlm_types.RLM_EVAL_TIMEOUT_MS == int(
        env("AUTOBOT_RLM_EVAL_TIMEOUT_MS")
    )


@pytest.fixture
def recorder(monkeypatch):
    fake = QualityGateMetricsRecorder(CollectorRegistry())
    monkeypatch.setattr(quality_gates, "quality_gate_metrics", lambda: fake)
    return fake


def _not_evaluated(recorder):
    return recorder.registry.get_sample_value("autobot_turn_not_evaluated_total", {"reason": "evaluator_failed"})


@pytest.mark.asyncio
async def test_a_turn_still_unjudged_after_the_retry_is_counted_once(recorder):
    evaluator = ResponseQualityEvaluator(config=RLMConfig())
    with patch.object(evaluator, "_call_llm", new=AsyncMock(side_effect=TimeoutError())):
        result = await evaluate_with_one_retry(evaluator, query="q", response="an answer")
    assert result.evaluator_failed and _not_evaluated(recorder) == 1.0


@pytest.mark.asyncio
async def test_a_turn_that_was_judged_is_not_counted(recorder):
    class _Judged:
        async def evaluate(self, **_kw):
            return ReflectionResult(ReflectionVerdict.ACCEPT, 0.9)

    await evaluate_with_one_retry(_Judged(), query="q", response="r")
    assert _not_evaluated(recorder) is None
