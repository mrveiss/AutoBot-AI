# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed evaluator is asked once more, then a plain reply is kept unverified; the model is not regenerated (#21845)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow.graph import route_after_reflection
from chat_workflow.reflection_gate import (
    ALTERNATIVE_APPROACH_HINT,
    evaluate_with_one_retry,
    reflection_update,
    regeneration_hint,
    wants_another_pass,
)
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
    state = {"reflection_history": history, "llm_response": "an answer", "reflection_count": 1}
    assert route_after_reflection(state) == "inline_judge_response"


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
    assert route_after_reflection({**state, "reflection_count": 1, "reflection_max": 0}) == "inline_judge_response"
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


# --- the alternative-approach instruction rides the regeneration that already happens (#22166) ---


def _update_hint(result: ReflectionResult) -> str:
    return reflection_update({"reflection_count": 0}, result, [result.to_dict()], MAX)["rlm_refinement_hint"]


def test_a_scored_refine_tells_the_next_pass_to_try_a_different_approach():
    refine = ReflectionResult(ReflectionVerdict.REFINE, 0.3, "thin", "Cover the edge cases.")
    hint = _update_hint(refine)
    assert hint.startswith("Cover the edge cases.")
    assert ALTERNATIVE_APPROACH_HINT in hint


def test_a_scored_refine_without_an_evaluator_hint_still_carries_the_instruction():
    assert _update_hint(ReflectionResult(ReflectionVerdict.REFINE, 0.3)) == ALTERNATIVE_APPROACH_HINT


def test_a_pass_carries_no_alternative_approach_instruction():
    accepted = ReflectionResult(ReflectionVerdict.ACCEPT, 0.9, "", "Fine as is.")
    assert _update_hint(accepted) == "Fine as is."
    assert ALTERNATIVE_APPROACH_HINT not in regeneration_hint(ReflectionResult(ReflectionVerdict.ACCEPT, 0.9))


def test_an_evaluator_failure_carries_the_evaluator_hint_and_no_alternative_approach():
    assert _update_hint(_failed()) == EVALUATOR_FAILED_HINT


def test_an_unscored_indeterminate_carries_no_alternative_approach():
    assert ALTERNATIVE_APPROACH_HINT not in regeneration_hint(ReflectionResult(ReflectionVerdict.INDETERMINATE, 0.5))


@pytest.mark.asyncio
async def test_the_alternative_approach_costs_no_extra_evaluation():
    evaluator = AsyncMock()
    evaluator.evaluate.return_value = ReflectionResult(ReflectionVerdict.REFINE, 0.3)
    result = await evaluate_with_one_retry(evaluator, query="q", response="r")
    regeneration_hint(result)
    assert evaluator.evaluate.await_count == 1
