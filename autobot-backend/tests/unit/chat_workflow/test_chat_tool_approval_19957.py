# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A held non-command chat tool call is approved and run, or refused, via the graph interrupt (#19957, #19951).

The held tool is ``click``: unset, it is a mutating browser action in a baseline category, so the real gate
(``_tool_call_needs_approval``) holds it, the card is raised, and the dispatch seam lets the bound call through once.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from chat_workflow.approval_binding import bind_decision
from chat_workflow.session_role import approval_gate_enabled
from tests.unit.chat_workflow.test_ai_line_support import VERIFIED_COMPANY, ai_line_world, arun_guard

CLICK = {"name": "click", "params": {"selector": "#buy"}}
READ = {"name": "web_search", "params": {"query": "weather in Riga"}}


def _graph():
    try:
        import chat_workflow.graph as graph_module
    except ImportError as exc:  # env-dependent chain; a real regression still fails
        pytest.skip(f"chat_workflow not importable here: {exc}")
    return graph_module


def _state(tool_calls, **extra):
    return {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "user_message": "weather in Riga",
        "context": {"verified_company_id": VERIFIED_COMPANY},
        "llm_params": {
            "ollama_endpoint": "http://x",
            "selected_model": "m",
            "system_prompt": "s",
            "initial_prompt": "p",
        },
        "execution_history": [{"tool": "web_search", "status": "success", "output": "rain"}],
        "workflow_messages": [],
        "iteration_count": 1,
        "tool_calls": tool_calls,
        **extra,
    }


def _manager(dispatched):
    from chat_workflow.manager import ChatWorkflowManager

    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)

    async def dispatch(tool_calls, *_a, ctx=None, **_k):
        dispatched.append([c["name"] for c in tool_calls])
        results = [{"tool": c["name"], "status": "success", "output": f"ran {c['name']}"} for c in tool_calls]
        yield {"type": "execution_summary", "metadata": {"execution_results": results}}
        yield (False, None)

    async def keep(results):
        return results

    manager._process_tool_calls = dispatch
    manager._offload_oversized_output = keep
    return manager


async def _planned(graph, call):
    """The call as the planner marks it: ``needs_approval`` comes from the real resolver, never set by hand."""
    ctx = SimpleNamespace(requires_approval_before=[], context={"verified_company_id": VERIFIED_COMPANY})
    with ai_line_world():
        return {**call, "needs_approval": await graph._tool_call_needs_approval(call, ctx)}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, True), ("1", True), ("true", True), ("YES", True), ("0", False), ("false", False), ("", False)],
)
def test_the_approval_gate_is_on_unless_switched_off(raw, expected):
    assert approval_gate_enabled(raw) is expected


@pytest.mark.asyncio
async def test_a_held_tool_raises_a_card_naming_the_tool_and_its_params():
    graph = _graph()
    held = await _planned(graph, CLICK)
    assert held["needs_approval"] is True
    seen = {}

    def fake_interrupt(payload):
        seen["payload"] = payload
        return {"approved": True, "reason": ""}

    with patch.object(graph, "interrupt", fake_interrupt):
        out = await graph.request_approval(_state([held, await _planned(graph, READ)]), {"configurable": {}})
    meta = seen["payload"]["metadata"]
    assert seen["payload"]["type"] == "command_approval_request"
    assert meta["command"].startswith("click ") and "#buy" in meta["command"]
    assert [c["tool"] for c in meta["calls"]] == ["click"] and meta["terminal_session_id"] == "t1"
    assert len(out["approval_decision"]["bound"]) == 1


@pytest.mark.asyncio
async def test_several_held_calls_say_how_many_more_the_card_covers():
    graph = _graph()
    held = [await _planned(graph, CLICK), await _planned(graph, {"name": "fill", "params": {"selector": "#q"}})]
    seen = {}

    def fake_interrupt(payload):
        seen["payload"] = payload
        return {"approved": False}

    with patch.object(graph, "interrupt", fake_interrupt):
        await graph.request_approval(_state(held), {"configurable": {}})
    assert seen["payload"]["metadata"]["command"].endswith("(+1 more)")


@pytest.mark.asyncio
async def test_held_then_approved_runs_once_and_is_not_held_again_at_dispatch():
    graph = _graph()
    held = await _planned(graph, CLICK)
    assert held["needs_approval"] is True
    decision = bind_decision({"approved": True}, [held])
    state = _state([held], approval_decision=decision)

    # The dispatch seam, given the bound decision, lets exactly the shown call through: no second hold, no record.
    seam_ctx = graph._build_llm_iteration_context(state)
    assert await arun_guard(dict(CLICK), seam_ctx, []) == (None, 0)

    dispatched: list = []
    out = await graph.execute_tools(state, {"configurable": {"manager": _manager(dispatched)}})
    assert dispatched == [["click"]]
    assert out["execution_history"][-1]["output"] == "ran click" and out["approval_decision"] is None


@pytest.mark.asyncio
async def test_refusing_tells_the_model_and_runs_only_the_calls_nobody_was_asked_about():
    graph = _graph()
    held, read = await _planned(graph, CLICK), await _planned(graph, READ)
    assert (held["needs_approval"], read["needs_approval"]) == (True, False)
    dispatched: list = []
    manager = _manager(dispatched)
    state = _state([held, read], approval_decision={"approved": False, "reason": "not now", "bound": []})

    out = await graph.execute_tools(state, {"configurable": {"manager": manager}})

    assert dispatched == [["web_search"]], "the ungated read runs; the refused call never does"
    new = out["execution_history"][1:]
    assert [(r["tool"], r["status"]) for r in new] == [("web_search", "success"), ("click", "refused")]
    step = manager._format_execution_step(3, new[1])
    assert "refused" in step and "not now" in step and "did not run" in step
    assert out["should_continue"] is True and out["tool_calls"] == [] and out["approval_decision"] is None


@pytest.mark.asyncio
async def test_a_batch_that_is_all_refused_runs_nothing():
    graph = _graph()
    dispatched: list = []
    state = _state([await _planned(graph, CLICK)], approval_decision={"approved": False, "reason": "", "bound": []})
    out = await graph.execute_tools(state, {"configurable": {"manager": _manager(dispatched)}})
    assert dispatched == [] and out["execution_history"][-1]["status"] == "refused"


@pytest.mark.asyncio
async def test_with_the_line_store_down_no_card_is_raised_and_the_seam_refuses():
    """Line 3 (store unreadable) cannot be lifted by a yes, so asking would only mislead."""
    graph = _graph()
    ctx = SimpleNamespace(requires_approval_before=[], context={"verified_company_id": VERIFIED_COMPANY})
    with ai_line_world(store_unavailable=True):
        assert await graph._tool_call_needs_approval(CLICK, ctx) is False
    message, filed = await arun_guard(dict(CLICK), ctx, [], store_unavailable=True)
    assert message.type == "error" and filed == 0
