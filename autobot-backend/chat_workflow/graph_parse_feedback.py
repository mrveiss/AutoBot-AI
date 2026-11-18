# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Parse-failure feedback for the chat graph itself (#21843).

A reply whose TOOL_CALL did not parse ran nothing. The graph tells the model so and asks again, bounded, whether or
not RLM reflection is on. When the budget is spent the user gets ``NO_ANSWER_FALLBACK``, never the markup and never an
empty reply. Intermediate replies are stored cleaned, so raw markup is never persisted; the failure stays recorded
as a ``tool_call_parse`` step in ``execution_history``.
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.env_utils import env_int
from chat_workflow import limits
from chat_workflow.reflection_gate import NO_ANSWER_FALLBACK
from chat_workflow.tool_call_args import clean_reply_text, parse_failure_step

#: Times one turn re-asks the model after an unparsed TOOL_CALL (#21843); the turn is also capped by the step budget.
PARSE_RETRY_BUDGET: int = env_int("AUTOBOT_CHAT_PARSE_RETRY_BUDGET", default=2)

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
    if retries >= PARSE_RETRY_BUDGET or iteration >= limits.MAX_CONTINUATION_ITERATIONS:
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
