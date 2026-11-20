# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Parse-failure feedback for the chat graph itself (#21843).

A reply whose TOOL_CALL did not parse ran nothing. The graph tells the model so and asks again, bounded by
``limits.INVALID_CALL_LIMIT``, whether or not RLM reflection is on. When the budget is spent the user gets
``NO_ANSWER_FALLBACK``, never the markup and never an empty reply. Intermediate replies are stored cleaned, so
raw markup is never persisted; the failure stays recorded as a ``tool_call_parse`` step in ``execution_history``.
"""

from __future__ import annotations

from typing import Any, Dict

from chat_workflow import limits
from chat_workflow.reflection_gate import NO_ANSWER_FALLBACK
from chat_workflow.tool_call_args import clean_reply_text, parse_failure_step

#: ``ChatState`` keys this module owns; reset at the start of a turn.
INITIAL_PARSE_STATE: Dict[str, Any] = {"parse_retries": 0, "parse_retry_pending": False}


def _fallback(state: Dict[str, Any], update: Dict[str, Any], stream_cb) -> Dict[str, Any]:
    message = {"type": "response", "content": NO_ANSWER_FALLBACK, "metadata": {"parse_fallback": True}}
    if stream_cb:
        stream_cb(message)
    responses = [*update["all_llm_responses"][:-1], ""]
    return {
        **update,
        "workflow_messages": [*update["workflow_messages"], message],
        "all_llm_responses": responses,
        "llm_response": "",
        "parse_retry_pending": False,
    }


def apply_parse_feedback(state: Dict[str, Any], update: Dict[str, Any], stream_cb=None) -> Dict[str, Any]:
    """*update* (one generation's state update) with the parse failure fed back, or the fallback once spent."""
    iteration = update.get("iteration_count", 0)
    step = (
        None
        if update.get("tool_calls") or update.get("error")
        else parse_failure_step(update.get("llm_response", ""), iteration)
    )
    if step is None:
        return {**update, "parse_retry_pending": False}
    retries = state.get("parse_retries", 0)
    if retries >= limits.INVALID_CALL_LIMIT or iteration >= limits.MAX_CONTINUATION_ITERATIONS:
        return _fallback(state, update, stream_cb)
    responses = [*update["all_llm_responses"][:-1], clean_reply_text(update["llm_response"])]
    history = [*(update.get("execution_history") or state.get("execution_history") or []), step]
    return {
        **update,
        "all_llm_responses": responses,
        "execution_history": history,
        "parse_retries": retries + 1,
        "parse_retry_pending": True,
    }


def inline_update(ctx, llm_response, should_continue, iteration, all_responses, parsed_tool_calls, messages) -> dict:
    """The state update of one inline (dispatching) generation pass of ``generate_response``."""
    return {
        "llm_response": llm_response or "",
        "should_continue": should_continue,
        "iteration_count": iteration,
        "all_llm_responses": all_responses,
        "tool_calls": parsed_tool_calls,
        "execution_history": list(ctx.execution_history),  # #19715: the next prompt is built from this
        "workflow_messages": messages,
        "tool_loop_warning": "",  # reset so a loop warning is only active for one cycle (#3254)
    }
