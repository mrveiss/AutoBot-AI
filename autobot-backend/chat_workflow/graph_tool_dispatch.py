# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The dispatch and plugin-hook parts of graph.py's execute_tools node, moved unchanged (#19715)."""

from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def emit_tool_call_hook(session_id, tool_calls: List[Dict[str, Any]]) -> None:
    """Issue #3278: notify plugins before tool execution."""
    try:
        from autobot_shared.plugin_sdk import Hook, HookRegistry

        await HookRegistry().call_hook(
            Hook.ON_TOOL_CALL.value,
            session_id=session_id,
            tool_calls=tool_calls,
        )
    except Exception as _hook_exc:  # noqa: BLE001
        logger.debug("Plugin hook ON_TOOL_CALL failed (non-fatal): %s", _hook_exc)


async def emit_tool_complete_hook(session_id, exec_history: List[Dict[str, Any]]) -> None:
    """Issue #3278: notify plugins after tool execution."""
    try:
        from autobot_shared.plugin_sdk import Hook, HookRegistry

        await HookRegistry().call_hook(
            Hook.ON_TOOL_COMPLETE.value,
            session_id=session_id,
            execution_history=exec_history,
        )
    except Exception as _hook_exc:  # noqa: BLE001
        logger.debug("Plugin hook ON_TOOL_COMPLETE failed (non-fatal): %s", _hook_exc)


def send_denied_message(decision: Dict[str, Any], iteration: int, messages: list, stream_cb) -> None:
    deny_msg = {
        "type": "response",
        "content": f"Command denied: {decision.get('reason', 'User denied')}",
        "metadata": {"iteration": iteration},
    }
    messages.append(deny_msg)
    if stream_cb:
        stream_cb(deny_msg)


async def dispatch_approved_calls(
    manager, exec_ctx, state: Dict[str, Any], tool_calls: list, iteration: int, messages: list, stream_cb
) -> Tuple[List[Dict[str, Any]], bool]:
    """Run planned calls through the manager's dispatch; returns (execution_history, break_loop)."""
    # Execute via existing manager method
    exec_history = list(state.get("execution_history", []))
    break_loop = False

    # #14242: bind the spill run on THIS path too. `_run_continuation_loop_
    # iteration` binds it for the non-gated path (#13997), but that method is
    # never called here — GH#11202's whole point is that this node dispatches
    # instead of it — so a run reaching this seam was never bound and the
    # offload below would decline to write (no run to re-read it under).
    manager._bind_spill_run(state.get("session_id"))

    # GH#11202: thread the governed-identity context so the same production
    # seam gates (forbidden_work #11145, config-protection #11177,
    # fact-forcing #11178) apply here exactly as they do on the inline
    # continuation-loop path. Without ``ctx=``, every ``_enforce_*`` check in
    # ``_dispatch_tool_call`` no-ops on ``ctx is None``.
    # GH#11202: the work-item approval seam gate (_enforce_work_item_approval)
    # must NOT re-fire here. On this (graph) path, route_after_generation /
    # request_approval already decided approval-required tool calls BEFORE
    # reaching this node (needs_approval on each tc, set by
    # _tool_call_needs_approval) — a denial already returned above, so
    # anything reaching this dispatch loop was either never gated or was just
    # approved. Re-checking requires_approval_before here would re-block an
    # approved action (double-block); clearing it supersedes the seam gate on
    # the graph path while leaving it fully active for legacy/MCP callers
    # that never pass through the interrupt.
    exec_ctx.requires_approval_before = []

    async for item in manager._process_tool_calls(
        tool_calls,
        state["session_id"],
        state["terminal_session_id"],
        state["llm_params"]["ollama_endpoint"],
        state["llm_params"]["selected_model"],
        ctx=exec_ctx,
    ):
        if isinstance(item, tuple) and len(item) == 2:
            break_loop, _ = item
        else:
            msg_dict = item.to_dict() if hasattr(item, "to_dict") else item
            # Issue #13295 (review B1): _process_tool_calls is the same
            # producer _process_tool_results drives, but this interrupt-resume
            # dispatch never routes through it — tag here so these messages
            # interleave correctly instead of falling into the untagged
            # leftover fallback.
            msg_dict.setdefault("metadata", {})["iteration"] = iteration
            # Stream ALL messages for real-time display
            if stream_cb:
                stream_cb(msg_dict)
            # Only persist non-streaming chunks (#1064)
            is_streaming = msg_dict.get("metadata", {}).get("streaming", False)
            if not is_streaming:
                messages.append(msg_dict)
            # Track execution results (#14242). `item` is the yielded
            # WorkflowMessage — never a dict — so `isinstance(item, dict)` here
            # never matched and `exec_history` silently stayed whatever
            # `state["execution_history"]` already held: new tool results never
            # reached it, and neither did the offload this seam now applies.
            # `msg_dict["metadata"]["execution_results"]` is the flat per-tool
            # list `_build_execution_summary` produces — the same shape
            # `_handle_execution_summary` extends `execution_history` with on
            # the non-gated path — offloaded through the same #13997 seam so
            # oversized output does not reach the model on a resume either.
            if msg_dict.get("type") == "execution_summary":
                new_results = msg_dict.get("metadata", {}).get("execution_results", [])
                new_results = await manager._offload_oversized_output(new_results)
                exec_history.extend(new_results)
    return exec_history, break_loop
