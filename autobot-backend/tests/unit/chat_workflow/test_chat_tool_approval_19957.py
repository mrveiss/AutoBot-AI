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
    import chat_workflow.graph as graph_module  # an import regression must fail these tests, never skip them

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


async def _governed(context, read=None, relaxed=None):
    """The turn context as chat builds it with the gate ON: the baseline overlaid on ``requires_approval_before``."""
    from unittest.mock import AsyncMock

    from chat_workflow.session_role import apply_session_governance

    with (
        patch("chat_workflow.session_role.CHAT_APPROVAL_GATE_ENABLED", True),
        patch("chat_workflow.session_role.SessionRoleService.get_role", AsyncMock(return_value=None)),
        patch(
            "chat_workflow.session_role.SessionRoleService.read_approval_categories", read or AsyncMock(return_value=[])
        ),
        patch("chat_workflow.session_work_item.SessionWorkItemService.get_work_item", AsyncMock(return_value=None)),
        patch("chat_workflow.attachment_floor.stamp_attachment_floor", AsyncMock(side_effect=lambda c, _s: c)),
        ai_line_world(slm_relaxed=relaxed),
    ):
        # The verified company comes from the route's scope; apply_auth_role replaces anything in the bag.
        governed = await apply_session_governance("s1", dict(context), "user", {"org_id": VERIFIED_COMPANY})
    return governed


async def _needs_approval(call, governed, relaxed=None):
    from services.ai_line_enforcement import call_needs_approval

    ctx = SimpleNamespace(requires_approval_before=governed["requires_approval_before"], context=governed)
    with ai_line_world(slm_relaxed=relaxed):
        return await call_needs_approval(call, ctx)


@pytest.mark.asyncio
async def test_navigate_runs_in_real_chat_where_the_baseline_overlay_is_applied_and_click_is_held():
    governed = await _governed({})
    assert "browser actions" in governed["requires_approval_before"], "control: the overlay put the category in"
    assert await _needs_approval({"name": "navigate", "params": {"url": "https://example.test"}}, governed) is False
    assert governed["verified_company_id"] == VERIFIED_COMPANY, "control: click resolves to line 2, not line 3"
    assert await _needs_approval(CLICK, governed) is True


@pytest.mark.asyncio
async def test_a_work_item_that_declares_browser_actions_still_holds_navigate():
    governed = await _governed({"requires_approval_before": ["browser actions"]})
    assert await _needs_approval({"name": "navigate", "params": {"url": "https://example.test"}}, governed) is True


@pytest.mark.asyncio
async def test_a_client_cannot_stamp_the_declared_set_to_lift_a_work_items_gate():
    forged = {"requires_approval_before": ["browser actions"], "declared_approval_categories": []}
    governed = await _governed(forged)
    assert governed["declared_approval_categories"] == ["browser actions"]


def test_the_card_counts_the_other_calls_even_when_the_first_is_a_shell_command():
    from chat_workflow.approval_binding import approval_card

    shell = {"name": "execute_command", "params": {"command": "ls"}, "command": "ls", "needs_approval": True}
    card = approval_card({"session_id": "s", "terminal_session_id": "t"}, [shell, dict(CLICK, needs_approval=True)])
    assert card["metadata"]["command"] == "ls (+1 more)"
    alone = approval_card({"session_id": "s", "terminal_session_id": "t"}, [shell])
    assert alone["metadata"]["command"] == "ls"


NAVIGATE = {"name": "navigate", "params": {"url": "https://example.test"}}


@pytest.mark.asyncio
async def test_an_unreadable_session_declaration_fails_closed_and_holds_navigate():
    from unittest.mock import AsyncMock

    governed = await _governed(
        {"declared_approval_categories": []}, read=AsyncMock(side_effect=ConnectionError("down"))
    )
    from autobot_shared.tool_catalogue import valid_approval_categories

    assert (
        set(governed["declared_approval_categories"]) == valid_approval_categories()
    ), "every category, not a client's"
    assert await _needs_approval(NAVIGATE, governed) is True
    # The administrator relaxed "browser actions" in the baseline: the unreadable declaration still holds navigate.
    relaxed = ["browser actions"]
    governed = await _governed({}, read=AsyncMock(side_effect=ConnectionError("down")), relaxed=relaxed)
    assert await _needs_approval(NAVIGATE, governed, relaxed) is True


def test_declared_categories_fall_back_to_the_overlaid_list_when_unstamped_or_malformed():
    from autobot_shared.ai_lines import declared_categories_of

    overlaid = ["browser actions", "writing files"]
    assert declared_categories_of(SimpleNamespace(requires_approval_before=overlaid, context={})) == tuple(overlaid)
    for bad in ("browser actions", 7, None, {"x": 1}):
        ctx = SimpleNamespace(requires_approval_before=overlaid, context={"declared_approval_categories": bad})
        assert declared_categories_of(ctx) == tuple(overlaid), "a malformed stamp fails closed"
    stamped = SimpleNamespace(requires_approval_before=overlaid, context={"declared_approval_categories": ["a", 3]})
    assert declared_categories_of(stamped) == ("a",)


@pytest.mark.asyncio
async def test_a_delegate_declares_what_its_parent_declared_so_it_holds_what_the_parent_holds():
    from chat_workflow.delegation import _declared_for_child
    from chat_workflow.run_authority import NO_INHERITANCE, Inheritance
    from services.ai_line_enforcement import call_needs_approval

    parent = await _governed({})
    parent_ctx = SimpleNamespace(requires_approval_before=parent["requires_approval_before"], context=parent)
    inherited = Inheritance.of(parent_ctx)
    assert inherited.declared_categories == ()
    stamp = _declared_for_child(["writing files"], inherited)
    child = SimpleNamespace(requires_approval_before=parent["requires_approval_before"], context={**parent, **stamp})
    with ai_line_world():
        assert await call_needs_approval(NAVIGATE, child) is False and await call_needs_approval(CLICK, child) is True
    assert _declared_for_child(["writing files"], NO_INHERITANCE) == {}, "no parent: the child's own list counts"

    work_item = await _governed({"requires_approval_before": ["browser actions"]})
    held = Inheritance.of(
        SimpleNamespace(requires_approval_before=work_item["requires_approval_before"], context=work_item)
    )
    child = SimpleNamespace(
        requires_approval_before=work_item["requires_approval_before"], context=_declared_for_child([], held)
    )
    child.context["verified_company_id"] = VERIFIED_COMPANY
    with ai_line_world():
        assert await call_needs_approval(NAVIGATE, child) is True, "a parent's declared gate reaches the child"


@pytest.mark.asyncio
async def test_dispatching_approved_calls_drops_the_stamp_from_the_exec_ctx_copy_only():
    from chat_workflow.graph_tool_dispatch import dispatch_approved_calls

    key = "declared_approval_categories"
    state = {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "execution_history": [],
        "llm_params": {"ollama_endpoint": "http://x", "selected_model": "m"},
        "context": {key: ["browser actions"]},
    }
    exec_ctx = SimpleNamespace(context=dict(state["context"]), requires_approval_before=["browser actions"])

    class Manager:
        def _bind_spill_run(self, _sid):
            pass

        async def _process_tool_calls(self, *_a, ctx=None, **_k):
            yield (False, None)

    await dispatch_approved_calls(Manager(), exec_ctx, state, [dict(CLICK)], 1, [], None)

    assert key not in exec_ctx.context and exec_ctx.requires_approval_before == []
    assert state["context"] == {key: ["browser actions"]}, "graph state is untouched"


@pytest.mark.asyncio
async def test_a_delegate_spawned_in_an_approved_dispatch_still_inherits_the_declared_set():
    from chat_workflow.graph_tool_dispatch import dispatch_approved_calls
    from chat_workflow.run_authority import Inheritance

    key = "declared_approval_categories"
    state = {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "execution_history": [],
        "llm_params": {"ollama_endpoint": "http://x", "selected_model": "m"},
        "context": {key: ["browser actions"]},
    }
    exec_ctx = SimpleNamespace(context=dict(state["context"]), requires_approval_before=["browser actions"])
    seen = {}

    class Manager:
        def _bind_spill_run(self, _sid):
            pass

        async def _process_tool_calls(self, *_a, ctx=None, **_k):
            seen["declared"] = Inheritance.of(ctx).declared_categories  # what a delegate spawned here would inherit
            yield (False, None)

    await dispatch_approved_calls(Manager(), exec_ctx, state, [dict(CLICK)], 1, [], None)

    assert key not in exec_ctx.context, "the clear stays: approved calls are not re-held"
    assert seen["declared"] == ("browser actions",)


def test_a_refused_result_fails_the_plan_step():
    from chat_workflow import plan_runner

    assert plan_runner.STATUS_OUTCOME["refused"] == plan_runner.FAIL


@pytest.mark.asyncio
async def test_a_pass_where_every_call_was_refused_settles_the_plan_step():
    from unittest.mock import AsyncMock

    graph = _graph()
    settle = AsyncMock(return_value={"plan_progress": {"block": "", "step_id": None}})
    state = _state(
        [dict(CLICK, needs_approval=True)], approval_decision={"approved": False, "reason": "no", "bound": []}
    )
    with patch.object(graph, "advance_after_tools", settle):
        out = await graph.execute_tools(state, {"configurable": {"manager": object()}})
    (_manager_arg, _state_arg, entries), _ = settle.await_args
    assert [e["status"] for e in entries] == ["refused"]
    assert out["plan_progress"] == {"block": "", "step_id": None} and out["tool_calls"] == []


@pytest.mark.asyncio
async def test_a_claude_code_delegate_spawned_in_an_approved_dispatch_still_refuses_what_the_parent_gated():
    """Parent declares "writing files", the approved dispatch clears it, and claude_code still refuses Write."""
    import services.execution.claude_code_backend as ccb
    from chat_workflow import delegation
    from chat_workflow.graph_tool_dispatch import dispatch_approved_calls
    from chat_workflow.run_authority import Inheritance

    state = {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "execution_history": [],
        "llm_params": {"ollama_endpoint": "http://x", "selected_model": "m"},
        "context": {},
    }
    exec_ctx = SimpleNamespace(context={}, requires_approval_before=["writing files"], agent_context=None)
    inherited = {}

    class Manager:
        def _bind_spill_run(self, _sid):
            pass

        async def _process_tool_calls(self, *_a, ctx=None, **_k):
            inherited["value"] = Inheritance.of(ctx)  # what the delegate handler builds from its parent
            yield (False, None)

    await dispatch_approved_calls(Manager(), exec_ctx, state, [dict(CLICK)], 1, [], None)
    assert exec_ctx.requires_approval_before == [], "control: the clear happened"
    assert inherited["value"].authority.approval_gates == {"writing files"}

    from unittest.mock import AsyncMock

    mock_exec = AsyncMock(return_value=SimpleNamespace(stdout="ok", stderr=""))
    with patch.object(ccb.ClaudeCodeBackend, "execute", new=mock_exec):
        await delegation._run_claude_code_subagent("subtask", "research_agent", 0, "user", inherited["value"])
    assert {"Write", "Edit"} <= set(mock_exec.await_args.args[0].metadata["disallowed_tools"])


@pytest.mark.asyncio
async def test_an_unreadable_declaration_with_a_relaxed_baseline_still_gates_the_claude_code_delegate():
    """Unreadable declaration + "writing files" relaxed by the administrator: Write and Edit stay refused."""
    from unittest.mock import AsyncMock

    import services.execution.claude_code_backend as ccb
    from chat_workflow import delegation
    from chat_workflow.graph_tool_dispatch import dispatch_approved_calls
    from chat_workflow.run_authority import Inheritance

    relaxed = ["writing files"]
    governed = await _governed({}, read=AsyncMock(side_effect=ConnectionError("down")), relaxed=relaxed)
    assert "writing files" in governed["requires_approval_before"], "the parent's own seam gates it too"
    state = {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "execution_history": [],
        "llm_params": {"ollama_endpoint": "http://x", "selected_model": "m"},
        "context": governed,
    }
    exec_ctx = SimpleNamespace(
        context=dict(governed), requires_approval_before=list(governed["requires_approval_before"]), agent_context=None
    )
    inherited = {}

    class Manager:
        def _bind_spill_run(self, _sid):
            pass

        async def _process_tool_calls(self, *_a, ctx=None, **_k):
            inherited["value"] = Inheritance.of(ctx)
            yield (False, None)

    await dispatch_approved_calls(Manager(), exec_ctx, state, [dict(CLICK)], 1, [], None)
    assert exec_ctx.requires_approval_before == [], "control: the clear happened"
    assert "writing files" in inherited["value"].authority.approval_gates

    mock_exec = AsyncMock(return_value=SimpleNamespace(stdout="ok", stderr=""))
    with patch.object(ccb.ClaudeCodeBackend, "execute", new=mock_exec):
        await delegation._run_claude_code_subagent("subtask", "research_agent", 0, "user", inherited["value"])
    assert {"Write", "Edit"} <= set(mock_exec.await_args.args[0].metadata["disallowed_tools"])
