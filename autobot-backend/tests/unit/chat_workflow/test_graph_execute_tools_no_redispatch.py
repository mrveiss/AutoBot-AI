# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11958: default (AUTOBOT_CHAT_APPROVAL_GATE OFF) graph path must not
re-dispatch already-executed tool-call summaries.

Root cause: generate_response's flag-OFF tail (chat_workflow/graph.py) reads
ctx.execution_history — POST-EXECUTION summary dicts shaped
``{"tool": ..., "status": ...}`` produced by the inline dispatch inside
manager._run_continuation_loop_iteration -> _process_tool_calls ->
_dispatch_tool_call — and returns them under state["tool_calls"].
route_after_generation then routes any turn with a non-empty tool_calls list
to execute_tools, which called manager._process_tool_calls(tool_calls, ...)
again on that same already-executed, wrongly-shaped list.
_dispatch_tool_call does ``tool_call["name"]`` directly, raising
``KeyError: 'name'`` on the post-execution shape (no "name" key).

This test pins that: (1) a tool-using turn no longer raises, (2) the tool is
dispatched exactly once (inline, never re-dispatched by execute_tools), and
(3) the flag-ON plan/execute split (#11202) is untouched.
"""

from __future__ import annotations

import pytest


def _graph_module():
    try:
        import chat_workflow.graph as graph_module
    except ImportError as exc:  # env-dependent chain; a real regression still fails
        pytest.skip(f"chat_workflow not importable here: {exc}")
    return graph_module


def _manager_new():
    from chat_workflow.manager import ChatWorkflowManager

    return ChatWorkflowManager.__new__(ChatWorkflowManager)


def _state(extra=None):
    base = {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "user_message": "search for something",
        "context": {},
        "llm_params": {
            "ollama_endpoint": "http://x/api/generate",
            "selected_model": "m",
            "system_prompt": "s",
            "initial_prompt": "p",
        },
        "used_knowledge": False,
        "rag_citations": [],
        "execution_history": [],
        "workflow_messages": [],
        "iteration_count": 0,
        "all_llm_responses": [],
        "tool_calls": [],
    }
    if extra:
        base.update(extra)
    return base


@pytest.mark.asyncio
async def test_flag_off_tool_turn_executes_once_and_never_redispatches(monkeypatch):
    """GH#11958 repro-and-fix: flag OFF, a tool-using turn must not KeyError
    and the tool must be dispatched exactly once (never re-dispatched)."""
    graph = _graph_module()
    monkeypatch.setattr("chat_workflow.session_role.CHAT_APPROVAL_GATE_ENABLED", False)

    manager = _manager_new()
    inline_dispatch_calls = {"count": 0}
    redispatch_calls = {"count": 0}

    async def fake_inline_iteration(http_client, current_prompt, iteration, ctx):
        """Simulates _run_continuation_loop_iteration: dispatches the tool
        inline (via _process_tool_calls -> _dispatch_tool_call) and leaves a
        POST-EXECUTION summary on ctx.execution_history — never the
        pre-execution {"name": ...} shape."""
        inline_dispatch_calls["count"] += 1
        ctx.execution_history.append({"tool": "web_search", "status": "success", "output": "results"})
        yield ("Here is what I found.", False)

    async def fake_redispatch(tool_calls, session_id, terminal_session_id, endpoint, model, ctx=None):
        """Stand-in for the real manager._process_tool_calls. Must NEVER be
        called on the flag-OFF path — that would mean execute_tools
        re-dispatched an already-executed summary (the #11958 defect)."""
        redispatch_calls["count"] += 1
        # Faithful to the real _dispatch_tool_call contract: direct-index
        # "name" access, which is exactly what raised KeyError pre-fix.
        _ = tool_calls[0]["name"]
        yield {"type": "execution_summary", "content": ""}
        yield (False, None)

    manager._run_continuation_loop_iteration = fake_inline_iteration
    manager._process_tool_calls = fake_redispatch

    config = {"configurable": {"manager": manager, "stream_callback": None}}
    state = _state()

    gen_result = await graph.generate_response(state, config)

    assert inline_dispatch_calls["count"] == 1, "tool must be dispatched exactly once, inline"
    assert gen_result["llm_response"] == "Here is what I found."
    # Pre-fix this was the crash trigger: a non-empty, wrongly-shaped list.
    assert gen_result["tool_calls"] == [{"tool": "web_search", "status": "success", "output": "results"}]

    merged_state = {**state, **gen_result}
    assert graph.route_after_generation(merged_state) == "execute_tools"

    # execute_tools must not crash (no KeyError) and must not re-dispatch.
    exec_result = await graph.execute_tools(merged_state, config)

    assert redispatch_calls["count"] == 0, "execute_tools must not re-dispatch already-executed summaries"
    assert exec_result["tool_calls"] == []
    assert exec_result["should_continue"] is False


@pytest.mark.asyncio
async def test_flag_on_execute_tools_still_dispatches_pre_execution_list(monkeypatch):
    """Regression guard: the #11202 flag-ON plan/execute split must still
    dispatch exactly once via execute_tools — the #11958 fix must not make
    execute_tools a no-op unconditionally."""
    graph = _graph_module()
    monkeypatch.setattr("chat_workflow.session_role.CHAT_APPROVAL_GATE_ENABLED", True)

    manager = _manager_new()
    dispatch_calls = {"count": 0}

    async def fake_dispatch(tool_calls, session_id, terminal_session_id, endpoint, model, ctx=None):
        dispatch_calls["count"] += 1
        assert tool_calls == [{"name": "web_search", "params": {"query": "x"}, "needs_approval": False}]
        yield {"type": "execution_summary", "content": ""}
        yield (False, None)

    manager._process_tool_calls = fake_dispatch

    config = {"configurable": {"manager": manager, "stream_callback": None}}
    state = _state(extra={"tool_calls": [{"name": "web_search", "params": {"query": "x"}, "needs_approval": False}]})

    exec_result = await graph.execute_tools(state, config)

    assert dispatch_calls["count"] == 1
    assert exec_result["tool_calls"] == []
