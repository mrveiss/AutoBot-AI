# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for success_criteria module.  Issue #3293."""

import pytest

from enhanced_orchestration.success_criteria import (
    CriteriaResult,
    EvaluationResult,
    SuccessCriteria,
    SuccessCriteriaEvaluator,
    SuccessCriteriaType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_criterion(
    criteria_type: SuccessCriteriaType,
    params: dict | None = None,
    weight: float = 1.0,
    required: bool = True,
    description: str = "",
) -> SuccessCriteria:
    return SuccessCriteria(
        criteria_type=criteria_type,
        parameters=params or {},
        weight=weight,
        required=required,
        description=description,
    )


EVALUATOR = SuccessCriteriaEvaluator()


# ---------------------------------------------------------------------------
# EvaluationResult.to_dict
# ---------------------------------------------------------------------------


class TestEvaluationResultToDict:
    def test_full_success_shape(self):
        result = EvaluationResult(overall="full", score=1.0, results=[])
        d = result.to_dict()
        assert d["overall"] == "full"
        assert d["score"] == 1.0
        assert d["results"] == []

    def test_partial_includes_criteria_fields(self):
        criterion = _make_criterion(
            SuccessCriteriaType.EXIT_CODE,
            params={"expected": 0},
            weight=2.0,
            required=False,
            description="exits cleanly",
        )
        cr = CriteriaResult(criteria=criterion, passed=True, detail="exit_code=0")
        result = EvaluationResult(overall="partial", score=0.5, results=[cr])
        item = result.to_dict()["results"][0]
        assert item["type"] == "exit_code"
        assert item["description"] == "exits cleanly"
        assert item["passed"] is True
        assert item["weight"] == 2.0
        assert item["required"] is False
        assert "exit_code=0" in item["detail"]


# ---------------------------------------------------------------------------
# EXIT_CODE
# ---------------------------------------------------------------------------


class TestExitCodeCriteria:
    @pytest.mark.asyncio
    async def test_passes_when_code_matches(self):
        c = _make_criterion(SuccessCriteriaType.EXIT_CODE, {"expected": 0})
        ev = await EVALUATOR.evaluate([c], {"exit_code": 0})
        assert ev.overall == "full"
        assert ev.score == 1.0
        assert ev.results[0].passed is True

    @pytest.mark.asyncio
    async def test_fails_when_code_differs(self):
        c = _make_criterion(SuccessCriteriaType.EXIT_CODE, {"expected": 0})
        ev = await EVALUATOR.evaluate([c], {"exit_code": 1})
        assert ev.overall == "failed"
        assert ev.results[0].passed is False

    @pytest.mark.asyncio
    async def test_fails_when_key_absent(self):
        c = _make_criterion(SuccessCriteriaType.EXIT_CODE, {"expected": 0})
        ev = await EVALUATOR.evaluate([c], {})
        assert ev.results[0].passed is False
        assert "not present" in ev.results[0].detail


# ---------------------------------------------------------------------------
# OUTPUT_PATTERN
# ---------------------------------------------------------------------------


class TestOutputPatternCriteria:
    @pytest.mark.asyncio
    async def test_passes_when_pattern_found(self):
        c = _make_criterion(SuccessCriteriaType.OUTPUT_PATTERN, {"pattern": r"SUCCESS"})
        ev = await EVALUATOR.evaluate([c], {"output": "Build SUCCESS complete"})
        assert ev.results[0].passed is True

    @pytest.mark.asyncio
    async def test_fails_when_pattern_absent(self):
        c = _make_criterion(SuccessCriteriaType.OUTPUT_PATTERN, {"pattern": r"SUCCESS"})
        ev = await EVALUATOR.evaluate([c], {"output": "Build FAILED"})
        assert ev.results[0].passed is False

    @pytest.mark.asyncio
    async def test_fails_with_empty_pattern(self):
        c = _make_criterion(SuccessCriteriaType.OUTPUT_PATTERN, {"pattern": ""})
        ev = await EVALUATOR.evaluate([c], {"output": "anything"})
        assert ev.results[0].passed is False
        assert "No pattern" in ev.results[0].detail


# ---------------------------------------------------------------------------
# RESOURCE_EXISTS
# ---------------------------------------------------------------------------


class TestResourceExistsCriteria:
    @pytest.mark.asyncio
    async def test_passes_when_key_present_and_truthy(self):
        c = _make_criterion(SuccessCriteriaType.RESOURCE_EXISTS, {"key": "artifact_url"})
        ev = await EVALUATOR.evaluate([c], {"resources": {"artifact_url": "https://example.com/file.tar"}})
        assert ev.results[0].passed is True

    @pytest.mark.asyncio
    async def test_fails_when_key_missing(self):
        c = _make_criterion(SuccessCriteriaType.RESOURCE_EXISTS, {"key": "artifact_url"})
        ev = await EVALUATOR.evaluate([c], {"resources": {}})
        assert ev.results[0].passed is False

    @pytest.mark.asyncio
    async def test_fails_when_no_key_specified(self):
        c = _make_criterion(SuccessCriteriaType.RESOURCE_EXISTS, {})
        ev = await EVALUATOR.evaluate([c], {"resources": {"x": "y"}})
        assert ev.results[0].passed is False


# ---------------------------------------------------------------------------
# CUSTOM
# ---------------------------------------------------------------------------


class TestCustomCriteria:
    @pytest.mark.asyncio
    async def test_passes_with_sync_fn(self):
        c = _make_criterion(
            SuccessCriteriaType.CUSTOM,
            {"fn": lambda r: r.get("score", 0) >= 0.9},
        )
        ev = await EVALUATOR.evaluate([c], {"score": 0.95})
        assert ev.results[0].passed is True

    @pytest.mark.asyncio
    async def test_passes_with_async_fn(self):
        async def async_check(result):
            return result.get("ready") is True

        c = _make_criterion(SuccessCriteriaType.CUSTOM, {"fn": async_check})
        ev = await EVALUATOR.evaluate([c], {"ready": True})
        assert ev.results[0].passed is True

    @pytest.mark.asyncio
    async def test_fails_without_fn(self):
        c = _make_criterion(SuccessCriteriaType.CUSTOM, {})
        ev = await EVALUATOR.evaluate([c], {})
        assert ev.results[0].passed is False
        assert "No callable" in ev.results[0].detail


# ---------------------------------------------------------------------------
# Aggregate: partial / full / failed
# ---------------------------------------------------------------------------


class TestAggregate:
    @pytest.mark.asyncio
    async def test_full_when_all_pass(self):
        c1 = _make_criterion(SuccessCriteriaType.EXIT_CODE, {"expected": 0})
        c2 = _make_criterion(SuccessCriteriaType.OUTPUT_PATTERN, {"pattern": "ok"})
        ev = await EVALUATOR.evaluate([c1, c2], {"exit_code": 0, "output": "ok"})
        assert ev.overall == "full"
        assert ev.score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_partial_when_optional_fails(self):
        required = _make_criterion(SuccessCriteriaType.EXIT_CODE, {"expected": 0}, required=True)
        optional = _make_criterion(
            SuccessCriteriaType.OUTPUT_PATTERN,
            {"pattern": "MISSING"},
            required=False,
        )
        ev = await EVALUATOR.evaluate([required, optional], {"exit_code": 0, "output": "something else"})
        assert ev.overall == "partial"
        assert 0.0 < ev.score < 1.0

    @pytest.mark.asyncio
    async def test_failed_when_required_fails(self):
        required = _make_criterion(SuccessCriteriaType.EXIT_CODE, {"expected": 0}, required=True)
        optional = _make_criterion(
            SuccessCriteriaType.OUTPUT_PATTERN,
            {"pattern": "ok"},
            required=False,
        )
        ev = await EVALUATOR.evaluate([required, optional], {"exit_code": 1, "output": "ok"})
        assert ev.overall == "failed"

    @pytest.mark.asyncio
    async def test_empty_criteria_list_returns_full(self):
        ev = await EVALUATOR.evaluate([], {"anything": True})
        assert ev.overall == "full"
        assert ev.score == 1.0

    @pytest.mark.asyncio
    async def test_weighted_score(self):
        heavy = _make_criterion(
            SuccessCriteriaType.EXIT_CODE,
            {"expected": 0},
            weight=3.0,
            required=False,
        )
        light = _make_criterion(
            SuccessCriteriaType.OUTPUT_PATTERN,
            {"pattern": "MISSING"},
            weight=1.0,
            required=False,
        )
        ev = await EVALUATOR.evaluate([heavy, light], {"exit_code": 0, "output": "no match"})
        # heavy passes (weight 3), light fails (weight 1) → 3/4 = 0.75
        assert ev.score == pytest.approx(0.75)
        assert ev.overall == "partial"

    @pytest.mark.asyncio
    async def test_evaluator_handles_exception_in_fn(self):
        def boom(_r):
            raise RuntimeError("kaboom")

        c = _make_criterion(SuccessCriteriaType.CUSTOM, {"fn": boom}, required=False)
        ev = await EVALUATOR.evaluate([c], {})
        assert ev.results[0].passed is False
        assert "Evaluation error" in ev.results[0].detail
