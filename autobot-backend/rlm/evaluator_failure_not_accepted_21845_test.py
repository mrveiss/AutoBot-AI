# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed evaluator is asked once more, then a plain reply is kept unverified; the model is not regenerated (#21845)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow.graph import route_after_reflection
from chat_workflow.reflection_gate import evaluate_with_one_retry, reflection_update, wants_another_pass
from rlm.evaluator import EVALUATOR_FAILED_HINT, ResponseQualityEvaluator
from rlm.types import ReflectionResult, ReflectionVerdict, RLMConfig

MAX = RLMConfig().max_reflections


def _failed(iteration: int = 1) -> ReflectionResult:
    return ReflectionResult(
        ReflectionVerdict.INDETERMINATE, 0.0, "boom", EVALUATOR_FAILED_HINT, iteration, evaluator_failed=True
    )


@pytest.mark.asyncio
async def test_an_evaluator_failure_is_flagged_and_carries_a_hint():
    evaluator = ResponseQualityEvaluator(config=RLMConfig())
    with patch.object(evaluator, "_call_llm", new=AsyncMock(side_effect=RuntimeError("down"))):
        result = await evaluator.evaluate(query="q", response="an answer")
    assert result.evaluator_failed and result.refinement_hint == EVALUATOR_FAILED_HINT
    assert result.to_dict()["evaluator_failed"] is True


def test_a_failed_evaluator_does_not_send_the_turn_back_to_generation():
    history = [_failed().to_dict()]
    assert route_after_reflection({"reflection_history": history, "reflection_count": 1}) == "inline_judge_response"


def test_a_real_indeterminate_judgement_is_still_accepted():
    unsure = ReflectionResult(ReflectionVerdict.INDETERMINATE, 0.5).to_dict()
    assert not wants_another_pass(unsure, 1, MAX)


def test_a_scored_pass_is_accepted_and_a_scored_refine_still_loops():
    assert not wants_another_pass({"verdict": "ACCEPT"}, 1, MAX)
    assert wants_another_pass({"verdict": "REFINE"}, 1, MAX)


def test_the_router_reads_the_limit_the_reflect_node_ran_under():
    history = [{"verdict": "REFINE"}]
    state = {"reflection_history": history, "llm_response": "an answer", "reflection_count": 2, "reflection_max": 2}
    assert route_after_reflection(state) == "inline_judge_response"
    assert route_after_reflection({**state, "reflection_max": 5}) == "generate_response"
    update = reflection_update({"reflection_count": 0}, _failed(), history, 7)
    assert update["reflection_max"] == 7 and update["reflection_count"] == 1


@pytest.mark.asyncio
async def test_a_broken_evaluator_is_asked_once_more_and_never_a_third_time():
    evaluator = AsyncMock()
    evaluator.evaluate.side_effect = [_failed(), _failed()]
    assert (await evaluate_with_one_retry(evaluator, query="q", response="r")).evaluator_failed
    assert evaluator.evaluate.await_count == 2


@pytest.mark.asyncio
async def test_a_recovered_evaluator_reading_is_used():
    good = ReflectionResult(ReflectionVerdict.ACCEPT, 0.9)
    evaluator = AsyncMock()
    evaluator.evaluate.side_effect = [_failed(), good]
    assert await evaluate_with_one_retry(evaluator, query="q", response="r") is good
