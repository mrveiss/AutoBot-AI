# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The graph re-asks after an unparsed TOOL_CALL whether or not RLM is on, bounded, then falls back (#21843)."""

from __future__ import annotations

from chat_workflow import limits
from chat_workflow.graph import route_after_generation
from chat_workflow.graph_parse_feedback import apply_parse_feedback
from chat_workflow.reflection_gate import NO_ANSWER_FALLBACK

BROKEN = '<TOOL_CALL name="web_search" params=\'{"query": \'>look it up'


def _update(text: str = BROKEN, iteration: int = 2, calls: list | None = None) -> dict:
    return {
        "llm_response": text,
        "iteration_count": iteration,
        "all_llm_responses": ["earlier", text],
        "workflow_messages": [],
        "tool_calls": calls or [],
        "execution_history": [],
    }


def test_an_unparsed_call_is_recorded_cleaned_and_sent_back_to_generation():
    out = apply_parse_feedback({"parse_retries": 0}, _update())
    assert out["parse_retry_pending"] and out["parse_retries"] == 1
    assert out["execution_history"][-1]["tool"] == "tool_call_parse"
    assert "TOOL_CALL" not in out["all_llm_responses"][-1]
    assert route_after_generation({**out, "tool_calls": []}) == "generate_response"


def test_a_spent_budget_gives_the_readable_fallback_and_no_markup():
    seen: list = []
    out = apply_parse_feedback({"parse_retries": limits.INVALID_CALL_LIMIT}, _update(), seen.append)
    assert not out["parse_retry_pending"] and out["llm_response"] == ""
    assert out["workflow_messages"][-1]["content"] == NO_ANSWER_FALLBACK and seen == out["workflow_messages"]
    assert out["all_llm_responses"] == ["earlier", ""]


def test_a_clean_reply_or_a_parsed_call_is_left_alone():
    assert not apply_parse_feedback({}, _update("a plain answer"))["parse_retry_pending"]
    assert not apply_parse_feedback({}, _update(calls=[{"name": "x"}]))["parse_retry_pending"]


def test_a_stale_refine_does_not_regenerate_after_the_fallback_emptied_the_reply():
    """The fallback empties llm_response, reflect then evaluates nothing; its old REFINE must not loop back."""
    from chat_workflow.graph import route_after_reflection

    state = {"reflection_history": [{"verdict": "REFINE"}], "reflection_count": 1, "llm_response": ""}
    assert route_after_reflection(state) == "inline_judge_response"
    assert route_after_reflection({**state, "llm_response": "an answer"}) == "generate_response"


def test_reflect_refine_then_unparsed_replies_emit_exactly_one_fallback():
    from chat_workflow.graph import route_after_reflection

    state = {
        "parse_retries": 0,
        "reflection_history": [{"verdict": "REFINE"}],
        "reflection_count": 1,
        "execution_history": [],
        "all_llm_responses": [],
        "workflow_messages": [],
    }
    fallbacks, node = 0, "generate_response"
    for iteration in range(1, 12):  # far more than the budget; a loop would keep emitting
        assert node == "generate_response"
        update = {
            "llm_response": BROKEN,
            "iteration_count": iteration,
            "all_llm_responses": [*state["all_llm_responses"], BROKEN],
            "workflow_messages": state["workflow_messages"],
            "tool_calls": [],
        }
        state = {**state, **apply_parse_feedback(state, update)}
        fallbacks = sum(1 for m in state["workflow_messages"] if m["content"] == NO_ANSWER_FALLBACK)
        node = route_after_generation(state)
        if node == "reflect_on_response":  # reflect returns {} for an empty reply: history stays stale
            node = route_after_reflection(state)
            break
    assert node == "inline_judge_response" and fallbacks == 1
