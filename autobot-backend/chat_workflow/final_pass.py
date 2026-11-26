# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The capped turn's last LLM pass: one answer from the results, never a tool call (#19715, #20720).

The pass dispatches nothing, but a model that ignores ``FINAL_ANSWER_INSTRUCTION`` still writes a TOOL_CALL. Its
output is therefore held until it is known to be clean: the user is shown, and the transcript stores, the reply
with every tool-call block removed, or ``NO_ANSWER_FALLBACK`` when none remains. The pass fires the same hooks and
``agent.step.*`` events as a normal pass (``generate_response``), so audit logs and the reasoning trace see it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import aiohttp

from autobot_shared.logging_manager import get_logger
from chat_workflow.reflection_gate import NO_ANSWER_FALLBACK
from chat_workflow.tool_call_args import clean_reply_text
from chat_workflow.tool_call_grammar import TOOL_CALL_PATTERN, normalize_tool_call_brackets
from chat_workflow.tool_call_loop import FINAL_ANSWER_INSTRUCTION

logger = get_logger(__name__)


def _without_tool_calls(text: str) -> str:
    """*text* with every tool-call block removed, well-formed or not: this pass dispatches none of them."""
    return clean_reply_text(TOOL_CALL_PATTERN.sub("", normalize_tool_call_brackets(text or "")))


def settle_final_reply(
    new_messages: List[Dict[str, Any]], llm_response: str | None
) -> Tuple[List[Dict[str, Any]], str]:
    """The pass's messages and reply with tool-call markup removed; a reply message left empty is dropped."""
    kept: List[Dict[str, Any]] = []
    for message in new_messages:
        if message.get("type") == "response":
            content = _without_tool_calls(message.get("content") or "")
            if not content:
                continue
            message = {**message, "content": content}
        kept.append(message)
    return kept, _without_tool_calls(llm_response or "")


async def _run_held(state, config, iteration: int):
    """Run the pass with its stream held back; returns ``(messages_before, messages, llm_response, step)``."""
    from chat_workflow import graph
    from chat_workflow.cot_events import emit_step_start
    from chat_workflow.graph_hooks import _emit_agent_execute_hook

    manager = config["configurable"]["manager"]
    session_id = state.get("session_id")
    step = f"llm_iteration_{iteration}"
    start = emit_step_start(step, session_id=session_id, agent_type="chat_workflow", step_id=step)
    await _emit_agent_execute_hook(session_id, iteration)
    messages = list(state.get("workflow_messages", []))
    before = len(messages)
    ctx = graph._build_llm_iteration_context(state)
    graph._carry_tool_results_into_prompt(manager, ctx, state)
    ctx.initial_prompt = graph._inject_mid_conversation_warning(FINAL_ANSWER_INSTRUCTION, ctx.initial_prompt)
    try:
        messages, llm_response, _calls, _stop = await graph._run_llm_iteration_plan(
            manager, ctx, iteration, messages, None
        )
    except aiohttp.ClientError as exc:
        logger.error("Final answer call failed: %s", exc)
        from chat_workflow.graph_hooks import _emit_planned_agent_error_hooks

        await _emit_planned_agent_error_hooks(session_id, iteration, exc)
        llm_response = None
    return before, messages, llm_response, (step, start)


async def run_final_pass(state, config) -> dict:
    """The body of the graph's ``force_final_answer`` node."""
    from chat_workflow.cot_events import emit_step_complete
    from chat_workflow.graph_hooks import _emit_planned_agent_complete_hook

    stream_cb = config["configurable"].get("stream_callback")
    iteration = state.get("iteration_count", 0) + 1
    before, messages, llm_response, (step, started) = await _run_held(state, config, iteration)
    kept, reply = settle_final_reply(messages[before:], llm_response)
    if not reply:
        kept = [{"type": "response", "content": NO_ANSWER_FALLBACK, "metadata": {"iteration": iteration}}]
    messages = [*messages[:before], *kept]
    for message in kept:
        if stream_cb:
            stream_cb(message)
    session_id = state.get("session_id")
    await _emit_planned_agent_complete_hook(session_id, iteration, reply)
    emit_step_complete(
        step, started, output_summary="final answer" if reply else "no final answer", session_id=session_id
    )
    return {
        "workflow_messages": messages,
        "all_llm_responses": [*state.get("all_llm_responses", []), reply],
        "iteration_count": iteration,
        "should_continue": False,
    }
