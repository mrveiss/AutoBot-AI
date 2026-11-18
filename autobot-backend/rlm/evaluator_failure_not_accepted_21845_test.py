# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed evaluator is re-asked within the budget, then the reply falls back; it is never accepted (#21845)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow.graph import route_after_reflection
from chat_workflow.reflection_gate import NO_ANSWER_FALLBACK, reflection_update, wants_another_pass
from rlm.evaluator import EVALUATOR_FAILED_HINT, ResponseQualityEvaluator
from rlm.types import ReflectionResult, ReflectionVerdict, RLMConfig

MARKUP = "<TOOL_CALL name=\"browser_evaluate\" params='{bad json'>x</TOOL_CALL>"
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


def test_a_failed_evaluator_goes_back_to_generation_until_the_budget_is_spent():
    history = [_failed().to_dict()]
    assert route_after_reflection({"reflection_history": history, "reflection_count": 1}) == "generate_response"
    assert route_after_reflection({"reflection_history": history, "reflection_count": MAX}) == "inline_judge_response"


def test_a_real_indeterminate_judgement_is_still_accepted():
    unsure = ReflectionResult(ReflectionVerdict.INDETERMINATE, 0.5).to_dict()
    assert not wants_another_pass(unsure, 1, MAX)


def test_a_scored_pass_is_accepted_and_a_scored_refine_still_loops():
    assert not wants_another_pass({"verdict": "ACCEPT"}, 1, MAX)
    assert wants_another_pass({"verdict": "REFINE"}, 1, MAX)


def _update(response: str, count: int, stream=None):
    state = {"reflection_count": count - 1, "llm_response": response, "all_llm_responses": ["earlier", response]}
    result = _failed()
    return reflection_update(state, result, [result.to_dict()], MAX, stream)


def test_out_of_passes_a_raw_tool_call_is_replaced_by_the_fallback():
    seen: list = []
    update = _update(MARKUP, MAX, seen.append)
    assert update["workflow_messages"][-1]["content"] == NO_ANSWER_FALLBACK
    assert seen == [update["workflow_messages"][-1]]
    assert update["all_llm_responses"] == ["earlier", ""]


def test_budget_left_no_fallback_yet():
    assert "workflow_messages" not in _update(MARKUP, 1)


def test_out_of_passes_a_readable_unscored_answer_is_kept():
    assert "workflow_messages" not in _update("Paris is the capital of France.", MAX)
