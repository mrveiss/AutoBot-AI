# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the graph does with a reflection result that is not a pass (#21845).

An evaluator that broke gave no reading, so its response is not accepted: the model is asked again within
``RLMConfig.max_reflections``. When the budget is spent and the reply is still raw TOOL_CALL markup, the user
gets the graceful fallback instead of the markup. A readable plain-text reply the evaluator could not score is
kept: it is an answer, merely unverified.
"""

from __future__ import annotations

from typing import Any, Dict

from chat_workflow.tool_call_args import tool_call_parse_error

#: The reply when no usable final answer was produced (also the fallback of ``force_final_answer``, #19715).
NO_ANSWER_FALLBACK = "I ran out of steps before finishing and could not write a final answer. Please try again."


def wants_another_pass(latest: Dict[str, Any], reflection_count: int, max_reflections: int) -> bool:
    """Whether the latest reflection result sends the turn back to generation (within the budget)."""
    not_accepted = latest.get("verdict") == "REFINE" or bool(latest.get("evaluator_failed"))
    return not_accepted and reflection_count < max_reflections


def reflection_update(state: Dict[str, Any], result: Any, history: list, max_reflections: int, stream_cb=None) -> dict:
    """The state update after one reflection pass, with the fallback once an unusable reply is out of passes."""
    count = state.get("reflection_count", 0) + 1
    update: Dict[str, Any] = {
        "reflection_count": count,
        "reflection_history": history,
        "rlm_refinement_hint": result.refinement_hint,
    }
    response = state.get("llm_response", "")
    if wants_another_pass(history[-1], count, max_reflections) or tool_call_parse_error(response) is None:
        return update
    message = {"type": "response", "content": NO_ANSWER_FALLBACK, "metadata": {"reflection_fallback": True}}
    if stream_cb:
        stream_cb(message)
    update["workflow_messages"] = [*state.get("workflow_messages", []), message]
    update["all_llm_responses"] = [*state.get("all_llm_responses", [])[:-1], ""]
    return update
