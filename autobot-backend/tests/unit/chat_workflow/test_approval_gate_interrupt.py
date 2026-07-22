# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11202: flag-gated approval-interrupt with a real pause-then-resume.

AUTOBOT_CHAT_APPROVAL_GATE (chat_workflow.session_role.CHAT_APPROVAL_GATE_ENABLED)
must be a hard no-op when OFF (default) — generate_response dispatches tool
calls inline exactly as before. When ON, generate_response becomes plan-only
(parses tool calls without dispatching), tags each with the combined
work-item + category needs_approval gate (_tool_call_needs_approval, reusing
_approval_category_for verbatim), and the graph's request_approval /
execute_tools nodes gate and dispatch exactly once.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

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


def _state(context=None, tool_calls=None, extra=None):
    base = {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "user_message": "do something",
        "context": context or {},
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
        "tool_calls": tool_calls or [],
    }
    if extra:
        base.update(extra)
    return base


# --- (a) flag OFF: zero behavior change, old inline-dispatch path used -----


@pytest.mark.asyncio
async def test_flag_off_uses_inline_dispatch_not_plan_only(monkeypatch):
    graph = _graph_module()
    monkeypatch.setattr("chat_workflow.session_role.CHAT_APPROVAL_GATE_ENABLED", False)

    manager = _manager_new()
    inline_called = {"count": 0}
    plan_called = {"count": 0}

    async def fake_inline(http_client, current_prompt, iteration, ctx):
        inline_called["count"] += 1
        yield ("assistant reply", True)

    async def fake_plan_only(http_client, current_prompt, iteration, ctx):
        plan_called["count"] += 1
        yield (None, None, True)

    manager._run_continuation_loop_iteration = fake_inline
    manager._run_llm_iteration_plan_only = fake_plan_only

    config = {"configurable": {"manager": manager, "stream_callback": None}}
    state = _state()

    result = await graph.generate_response(state, config)

    assert inline_called["count"] == 1
    assert plan_called["count"] == 0
    assert result["llm_response"] == "assistant reply"


@pytest.mark.asyncio
async def test_flag_off_never_reaches_planned_helper(monkeypatch):
    """Flag OFF must never even construct the plan-only tail (no-op guarantee)."""
    graph = _graph_module()
    monkeypatch.setattr("chat_workflow.session_role.CHAT_APPROVAL_GATE_ENABLED", False)

    async def _boom(*_a, **_k):
        raise AssertionError("_generate_response_planned must not run when flag is OFF")

    monkeypatch.setattr(graph, "_generate_response_planned", _boom)

    manager = _manager_new()

    async def fake_inline(http_client, current_prompt, iteration, ctx):
        yield ("ok", False)

    manager._run_continuation_loop_iteration = fake_inline
    config = {"configurable": {"manager": manager, "stream_callback": None}}

    result = await graph.generate_response(_state(), config)
    assert result["llm_response"] == "ok"


# --- (b)/(c) flag ON: needs_approval set BEFORE execution, via the combined gate ---


@pytest.mark.asyncio
async def test_flag_on_work_item_category_sets_needs_approval_before_execution(monkeypatch):
    """Gated via the work-item-declared category ('destructive operations' -> bash)."""
    graph = _graph_module()
    monkeypatch.setattr("chat_workflow.session_role.CHAT_APPROVAL_GATE_ENABLED", True)

    manager = _manager_new()
    dispatch_calls = {"count": 0}

    async def fake_plan_only(http_client, current_prompt, iteration, ctx):
        yield ("I'll run bash", [{"name": "bash", "params": {"command": "rm -rf /tmp/x"}}], False)

    async def fake_dispatch_should_not_run(*_a, **_k):
        dispatch_calls["count"] += 1
        yield {"type": "execution_summary", "content": ""}

    manager._run_llm_iteration_plan_only = fake_plan_only
    manager._process_tool_calls = fake_dispatch_should_not_run

    config = {"configurable": {"manager": manager, "stream_callback": None}}
    state = _state(context={"work_item_id": "wi-1", "requires_approval_before": ["destructive operations"]})

    result = await graph.generate_response(state, config)

    assert dispatch_calls["count"] == 0, "generate_response must never dispatch tools in the gated path"
    assert result["tool_calls"][0]["needs_approval"] is True
    assert graph.route_after_generation({**state, **result}) == "request_approval"


@pytest.mark.asyncio
async def test_flag_on_approval_category_sets_needs_approval_before_execution(monkeypatch):
    """Gated via a different declared category ('pushing commits' -> git_push)."""
    graph = _graph_module()
    monkeypatch.setattr("chat_workflow.session_role.CHAT_APPROVAL_GATE_ENABLED", True)

    manager = _manager_new()

    async def fake_plan_only(http_client, current_prompt, iteration, ctx):
        yield ("pushing now", [{"name": "git_push", "params": {}}], False)

    manager._run_llm_iteration_plan_only = fake_plan_only

    config = {"configurable": {"manager": manager, "stream_callback": None}}
    state = _state(context={"requires_approval_before": ["pushing commits"]})

    result = await graph.generate_response(state, config)

    assert result["tool_calls"][0]["needs_approval"] is True
    assert graph.route_after_generation({**state, **result}) == "request_approval"


# --- (e) flag ON, non-gated tool: executes normally, no interrupt ----------


@pytest.mark.asyncio
async def test_flag_on_non_gated_tool_executes_without_interrupt(monkeypatch):
    graph = _graph_module()
    monkeypatch.setattr("chat_workflow.session_role.CHAT_APPROVAL_GATE_ENABLED", True)

    manager = _manager_new()

    async def fake_plan_only(http_client, current_prompt, iteration, ctx):
        yield ("searching", [{"name": "web_search", "params": {"query": "x"}}], False)

    manager._run_llm_iteration_plan_only = fake_plan_only

    config = {"configurable": {"manager": manager, "stream_callback": None}}
    state = _state(context={"requires_approval_before": ["destructive operations"]})

    result = await graph.generate_response(state, config)

    assert result["tool_calls"][0]["needs_approval"] is False
    merged_state = {**state, **result}
    assert graph.route_after_generation(merged_state) == "execute_tools"

    # execute_tools dispatches it exactly once.
    dispatch_calls = {"count": 0}

    async def fake_dispatch(tool_calls, session_id, terminal_session_id, endpoint, model, ctx=None):
        dispatch_calls["count"] += 1
        yield {"type": "execution_summary", "content": ""}
        yield (False, None)

    manager._process_tool_calls = fake_dispatch
    exec_result = await graph.execute_tools(merged_state, config)

    assert dispatch_calls["count"] == 1
    assert exec_result["tool_calls"] == []


# --- (d) approve -> execute exactly once; deny -> skipped, no double-exec --


@pytest.mark.asyncio
async def test_approve_resumes_and_executes_exactly_once(monkeypatch):
    graph = _graph_module()
    manager = _manager_new()
    dispatch_calls = {"count": 0}

    async def fake_dispatch(tool_calls, session_id, terminal_session_id, endpoint, model, ctx=None):
        dispatch_calls["count"] += 1
        assert len(tool_calls) == 1
        yield {"type": "execution_summary", "content": ""}
        yield (False, None)

    manager._process_tool_calls = fake_dispatch
    config = {"configurable": {"manager": manager, "stream_callback": None}}

    tool_calls = [{"name": "bash", "params": {"command": "ls"}, "needs_approval": True}]
    state = _state(
        context={"requires_approval_before": ["destructive operations"]},
        tool_calls=tool_calls,
        extra={"approval_decision": {"approved": True, "reason": ""}},
    )

    result = await graph.execute_tools(state, config)

    assert dispatch_calls["count"] == 1
    assert result["tool_calls"] == []


@pytest.mark.asyncio
async def test_deny_skips_execution_entirely(monkeypatch):
    graph = _graph_module()
    manager = _manager_new()
    dispatch_calls = {"count": 0}

    async def fake_dispatch(*_a, **_k):
        dispatch_calls["count"] += 1
        yield {"type": "execution_summary", "content": ""}
        yield (False, None)

    manager._process_tool_calls = fake_dispatch
    config = {"configurable": {"manager": manager, "stream_callback": None}}

    tool_calls = [{"name": "bash", "params": {"command": "rm -rf /"}, "needs_approval": True}]
    state = _state(
        context={"requires_approval_before": ["destructive operations"]},
        tool_calls=tool_calls,
        extra={"approval_decision": {"approved": False, "reason": "too risky"}},
    )

    result = await graph.execute_tools(state, config)

    assert dispatch_calls["count"] == 0
    assert result["should_continue"] is False


# --- execute_tools must not re-block an already-approved/never-gated tool -


@pytest.mark.asyncio
async def test_execute_tools_clears_requires_approval_before_to_avoid_double_block(monkeypatch):
    """The seam gate (_enforce_work_item_approval) must not re-fire in execute_tools
    on the graph path — the interrupt already decided. Verified by asserting the
    ctx handed to _process_tool_calls carries an empty requires_approval_before."""
    graph = _graph_module()
    manager = _manager_new()
    seen_ctx = {}

    async def fake_dispatch(tool_calls, session_id, terminal_session_id, endpoint, model, ctx=None):
        seen_ctx["ctx"] = ctx
        yield {"type": "execution_summary", "content": ""}
        yield (False, None)

    manager._process_tool_calls = fake_dispatch
    config = {"configurable": {"manager": manager, "stream_callback": None}}

    tool_calls = [{"name": "bash", "params": {}, "needs_approval": True}]
    state = _state(
        context={"work_item_id": "wi-1", "requires_approval_before": ["destructive operations"]},
        tool_calls=tool_calls,
        extra={"approval_decision": {"approved": True, "reason": ""}},
    )

    await graph.execute_tools(state, config)

    assert seen_ctx["ctx"] is not None
    assert seen_ctx["ctx"].requires_approval_before == []


# --- manager._run_llm_iteration_plan_only never dispatches -----------------


@pytest.mark.asyncio
async def test_manager_plan_only_never_calls_process_tool_calls(monkeypatch):
    from chat_workflow.manager import ChatWorkflowManager, LLMIterationContext

    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    dispatch_calls = {"count": 0}

    async def fake_dispatch(*_a, **_k):
        dispatch_calls["count"] += 1
        yield {"type": "execution_summary"}

    manager._process_tool_calls = fake_dispatch

    async def fake_collect(http_client, current_prompt, iteration, ctx):
        yield ("assistant text", [{"name": "bash", "params": {}}], False)

    manager._collect_and_validate_llm_response = fake_collect

    ctx = LLMIterationContext(
        ollama_endpoint="http://x",
        selected_model="m",
        session_id="s1",
        terminal_session_id="t1",
        used_knowledge=False,
        rag_citations=[],
        workflow_messages=[],
        system_prompt="s",
        initial_prompt="p",
        message="hi",
        context={},
    )

    llm_response, tool_calls, should_stop = None, None, None
    async for item in manager._run_llm_iteration_plan_only(None, "p", 1, ctx):
        if isinstance(item, tuple) and len(item) == 3:
            llm_response, tool_calls, should_stop = item

    assert dispatch_calls["count"] == 0
    assert llm_response == "assistant text"
    assert tool_calls == [{"name": "bash", "params": {}}]
    assert should_stop is False


# --- _tool_call_needs_approval: combined gate reuses _approval_category_for -


def test_tool_call_needs_approval_combined_gate():
    graph = _graph_module()
    from types import SimpleNamespace

    gated_ctx = SimpleNamespace(requires_approval_before=["destructive operations"])
    ungated_ctx = SimpleNamespace(requires_approval_before=[])
    non_matching_ctx = SimpleNamespace(requires_approval_before=["publishing"])

    assert graph._tool_call_needs_approval({"name": "bash"}, gated_ctx) is True
    assert graph._tool_call_needs_approval({"name": "bash"}, ungated_ctx) is False
    assert graph._tool_call_needs_approval({"name": "bash"}, non_matching_ctx) is False
    assert graph._tool_call_needs_approval({"name": "web_search"}, gated_ctx) is False
