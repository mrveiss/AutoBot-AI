# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the graph does with a reflection result (#21845).

An evaluator that broke gave no reading. That is a fault of the evaluator, not of the reply: it is asked once more,
and if it is still broken a readable plain-text reply is kept as an answer that is merely unverified. The model is
never regenerated for it (a deterministic evaluator failure would cost a generation and an evaluation per pass and
replace a good answer). Raw TOOL_CALL markup never reaches this point: ``graph_parse_feedback`` re-asks the model or
ends on ``NO_ANSWER_FALLBACK`` first.
"""

from __future__ import annotations

from typing import Any, Dict

#: The reply when no usable final answer was produced (also the fallback of ``force_final_answer``, #19715).
NO_ANSWER_FALLBACK = "I ran out of steps before finishing and could not write a final answer. Please try again."


def wants_another_pass(latest: Dict[str, Any], reflection_count: int, max_reflections: int) -> bool:
    """Whether the latest reflection result sends the turn back to generation (within the budget)."""
    return latest.get("verdict") == "REFINE" and reflection_count < max_reflections


async def evaluate_with_one_retry(evaluator: Any, **kwargs: Any) -> Any:
    """``evaluator.evaluate(**kwargs)``, asked once more when it could not give a reading."""
    result = await evaluator.evaluate(**kwargs)
    if getattr(result, "evaluator_failed", False):
        result = await evaluator.evaluate(**kwargs)
    return result


def reflection_update(state: Dict[str, Any], result: Any, history: list, max_reflections: int) -> dict:
    """The state update after one reflection pass; carries the configured budget for the router."""
    return {
        "reflection_count": state.get("reflection_count", 0) + 1,
        "reflection_history": history,
        "rlm_refinement_hint": result.refinement_hint,
        "reflection_max": max_reflections,
    }
