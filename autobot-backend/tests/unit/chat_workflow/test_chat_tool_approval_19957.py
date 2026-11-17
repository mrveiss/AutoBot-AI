# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A held non-command chat tool call is approved and run, or refused, via the graph interrupt (#19957, #19951)."""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

NAVIGATE = {"name": "navigate", "params": {"url": "https://example.test/weather"}, "needs_approval": True}


def _graph():
    try:
        import chat_workflow.graph as graph_module
    except ImportError as exc:  # env-dependent chain; a real regression still fails
        pytest.skip(f"chat_workflow not importable here: {exc}")
    return graph_module


def _state(**extra):
    return {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "user_message": "weather in Riga",
        "context": {},
        "llm_params": {
            "ollama_endpoint": "http://x",
            "selected_model": "m",
            "system_prompt": "s",
            "initial_prompt": "p",
        },
        "execution_history": [{"tool": "web_search", "status": "success", "output": "rain"}],
        "workflow_messages": [],
        "iteration_count": 1,
        "tool_calls": [dict(NAVIGATE)],
        **extra,
    }


def _manager():
    from chat_workflow.manager import ChatWorkflowManager

    return ChatWorkflowManager.__new__(ChatWorkflowManager)


@pytest.mark.parametrize("env, expected", [(None, True), ("1", True), ("0", False), ("false", False)])
def test_the_approval_gate_is_on_unless_switched_off(monkeypatch, env, expected):
    from chat_workflow import session_role

    if env is None:
        monkeypatch.delenv("AUTOBOT_CHAT_APPROVAL_GATE", raising=False)
    else:
        monkeypatch.setenv("AUTOBOT_CHAT_APPROVAL_GATE", env)
    try:
        assert importlib.reload(session_role).CHAT_APPROVAL_GATE_ENABLED is expected
    finally:
        monkeypatch.undo()
        importlib.reload(session_role)


@pytest.mark.asyncio
async def test_the_card_for_a_held_non_command_tool_names_the_tool_and_its_params():
    graph = _graph()
    seen = {}

    def fake_interrupt(payload):
        seen["payload"] = payload
        return {"approved": True, "reason": ""}

    with patch.object(graph, "interrupt", fake_interrupt):
        out = await graph.request_approval(_state(), {"configurable": {}})
    meta = seen["payload"]["metadata"]
    assert seen["payload"]["type"] == "command_approval_request"
    assert meta["command"].startswith("navigate ") and "example.test/weather" in meta["command"]
    assert meta["calls"][0]["tool"] == "navigate" and meta["terminal_session_id"] == "t1"
    assert out["approval_decision"]["approved"] is True and len(out["approval_decision"]["bound"]) == 1


@pytest.mark.asyncio
async def test_approving_runs_exactly_the_shown_call_and_its_result_reaches_the_model():
    graph = _graph()
    manager = _manager()
    seen = {}

    async def fake_dispatch(tool_calls, *_a, ctx=None, **_k):
        seen["calls"], seen["ctx"] = tool_calls, ctx
        yield {
            "type": "execution_summary",
            "metadata": {"execution_results": [{"tool": "navigate", "status": "success", "output": "Riga: 4C"}]},
        }
        yield (False, None)

    async def keep(results):
        return results

    manager._process_tool_calls = fake_dispatch
    manager._offload_oversized_output = keep
    from chat_workflow.approval_binding import bind_decision

    decision = bind_decision({"approved": True}, [NAVIGATE])
    out = await graph.execute_tools(_state(approval_decision=decision), {"configurable": {"manager": manager}})

    assert [c["name"] for c in seen["calls"]] == ["navigate"]
    assert seen["ctx"].approved_fingerprints == frozenset(decision["bound"])
    assert out["execution_history"][-1]["output"] == "Riga: 4C" and out["should_continue"] is True
    assert out["approval_decision"] is None


@pytest.mark.asyncio
async def test_refusing_runs_nothing_and_tells_the_model_the_call_was_refused():
    graph = _graph()
    manager = _manager()
    ran = []

    async def fake_dispatch(*_a, **_k):
        ran.append(1)
        yield (False, None)

    manager._process_tool_calls = fake_dispatch
    out = await graph.execute_tools(
        _state(approval_decision={"approved": False, "reason": "not now", "bound": []}),
        {"configurable": {"manager": manager}},
    )
    assert ran == [] and out["should_continue"] is True and out["tool_calls"] == [] and out["approval_decision"] is None
    refusal = out["execution_history"][-1]
    assert refusal["tool"] == "navigate" and refusal["status"] == "refused"
    step = manager._format_execution_step(2, refusal)
    assert "refused" in step and "not now" in step and "did not run" in step
