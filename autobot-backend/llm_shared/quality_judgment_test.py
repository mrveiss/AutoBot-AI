# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-caller pins for the shared quality-judging seam (#16133).

Each plane is driven end to end by a fake LLM that returns fixed JSON, and its
verdict, score and serialized shape are asserted unchanged.
"""

import json

import pytest

from judges import BaseLLMJudge, JudgmentConfidence, JudgmentDimension
from llm_shared.quality_judgment import QualityAssessment, clamp_score, finite_score, meets_threshold
from rlm.evaluator import ResponseQualityEvaluator
from rlm.types import VERDICT_RECOMMENDATION, ReflectionVerdict, RLMConfig


class _FakeEvaluator(ResponseQualityEvaluator):
    def __init__(self, reply: dict, threshold: float = 0.7):
        super().__init__(RLMConfig(quality_threshold=threshold))
        self._reply = reply

    async def _call_llm(self, prompt: str) -> str:
        return json.dumps(self._reply)


class _FakeJudge(BaseLLMJudge):
    def __init__(self, reply: dict):
        super().__init__("fake")
        self._reply = reply

    async def _prepare_judgment_prompt(self, subject, criteria, context, alternatives=None, **kw):
        return f"judge {subject}"

    async def _get_llm_evaluation(self, prompt, *, system_prompt=None, json_schema=None):
        return json.dumps(self._reply)


_JUDGMENT = {
    "overall_score": 0.4,
    "recommendation": "REVISE",
    "confidence": "high",
    "reasoning": "thin",
    "criterion_scores": [
        {"dimension": "quality", "score": 0.4, "confidence": "high", "reasoning": "r"},
    ],
    "improvement_suggestions": ["add detail", "cite"],
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("score", "verdict"),
    [(0.7, ReflectionVerdict.ACCEPT), (0.69, ReflectionVerdict.REFINE)],
)
async def test_rlm_plane_verdicts_and_scale_are_unchanged(score, verdict):
    result = await _FakeEvaluator({"score": score, "critique": "none", "hint": "h"}).evaluate("q", "a", iteration=2)
    assert result.verdict is verdict
    assert result.quality_score == score
    assert result.critique == ""  # the literal "none" is still normalised away
    assert result.iteration == 2


@pytest.mark.asyncio
async def test_rlm_serialized_shape_is_unchanged():
    result = await _FakeEvaluator({"score": 0.2, "critique": "c", "hint": "h"}).evaluate("q", "a")
    assert set(result.to_dict()) == {
        "verdict",
        "quality_score",
        "critique",
        "refinement_hint",
        "iteration",
        "timestamp",
    }
    assert result.to_dict()["verdict"] == "REFINE"


@pytest.mark.asyncio
async def test_rlm_out_of_range_score_is_indeterminate_not_clamped():
    result = await _FakeEvaluator({"score": 1.5}).evaluate("q", "a")
    assert result.verdict is ReflectionVerdict.INDETERMINATE


@pytest.mark.asyncio
async def test_rlm_unreadable_reply_is_indeterminate_not_a_default_score():
    result = await _FakeEvaluator({"critique": "no score"}).evaluate("q", "a")
    assert result.verdict is ReflectionVerdict.INDETERMINATE


@pytest.mark.asyncio
async def test_judges_plane_result_is_unchanged():
    result = await _FakeJudge(_JUDGMENT).make_judgment("s", [JudgmentDimension.QUALITY], {})
    assert (result.overall_score, result.recommendation) == (0.4, "REVISE")
    assert result.confidence is JudgmentConfidence.HIGH
    assert result.criterion_scores[0].dimension is JudgmentDimension.QUALITY
    assert result.llm_model_used == "unknown"


@pytest.mark.asyncio
async def test_judges_plane_schema_drift_still_becomes_the_error_judgment():
    bad = dict(_JUDGMENT, recommendation="MAYBE")
    result = await _FakeJudge(bad).make_judgment("s", [JudgmentDimension.QUALITY], {})
    assert result.llm_model_used == "error" and result.recommendation == "REJECT"


@pytest.mark.asyncio
async def test_both_planes_project_onto_one_assessment():
    reflection = await _FakeEvaluator({"score": 0.4, "critique": "thin", "hint": "more"}).evaluate("q", "a")
    judgment = await _FakeJudge(_JUDGMENT).make_judgment("s", [JudgmentDimension.QUALITY], {})
    r, j = reflection.assessment(0.7), judgment.assessment(0.7)
    assert isinstance(r, QualityAssessment) and isinstance(j, QualityAssessment)
    assert (r.score, r.critique, r.hint, r.passed) == (0.4, "thin", "more", False)
    assert (j.score, j.critique, j.hint, j.passed) == (0.4, "thin", "add detail; cite", False)
    assert judgment.assessment().passed is None  # no threshold supplied, none invented


def test_verdict_and_recommendation_are_one_vocabulary():
    from judges import RECOMMENDATIONS

    assert set(VERDICT_RECOMMENDATION.values()) <= set(RECOMMENDATIONS)
    assert VERDICT_RECOMMENDATION[ReflectionVerdict.ACCEPT] == "APPROVE"


def test_score_arithmetic():
    assert clamp_score(-1) == 0.0 and clamp_score(2) == 1.0
    assert meets_threshold(0.7, 0.7) and not meets_threshold(0.6999, 0.7)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_score_raises_instead_of_clamping(bad):
    with pytest.raises(ValueError):
        clamp_score(bad)
    with pytest.raises(ValueError):
        finite_score(bad)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
async def test_rlm_non_finite_score_is_indeterminate(bad):
    result = await _FakeEvaluator({"score": bad}).evaluate("q", "a")
    assert result.verdict is ReflectionVerdict.INDETERMINATE


@pytest.mark.asyncio
async def test_judges_plane_non_finite_score_becomes_the_error_judgment():
    bad = dict(_JUDGMENT, overall_score=float("nan"))
    result = await _FakeJudge(bad).make_judgment("s", [JudgmentDimension.QUALITY], {})
    assert result.llm_model_used == "error" and result.recommendation == "REJECT"
