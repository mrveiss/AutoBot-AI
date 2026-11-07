# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat graph's planner node and step advance, with a fake planner (#21023, part of #20846)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_workflow import graph, graph_planner, plan_runner

pytestmark = pytest.mark.asyncio


class FakePlanner:
    """Records calls; three steps, one per tool pass."""

    def __init__(self):
        self.calls = []
        self.steps = ["s1", "s2", "s3"]
        self.done = 0

    async def create_plan(self, task):
        self.calls.append(("create_plan", task))
        steps = [SimpleNamespace(step_id=f"id{i}", step_number=i, description=d) for i, d in enumerate(self.steps, 1)]
        return SimpleNamespace(plan_id="P", steps=steps, total_steps=3, metadata={"fallback": False})

    async def get_plan(self, plan_id):
        steps = [
            SimpleNamespace(step_id=f"id{i}", step_number=i, description=d, status=None)
            for i, d in enumerate(self.steps, 1)
        ]
        cur = steps[self.done] if self.done < 3 else None
        return SimpleNamespace(
            plan_id="P",
            total_steps=3,
            completed_steps=self.done,
            get_next_executable_steps=lambda: [steps[self.done]] if self.done < 3 else [],
            get_current_step=lambda: cur if getattr(self, "started", False) else None,
        )

    async def start_step(self, plan_id, step_id):
        self.calls.append(("start_step", step_id))
        self.started = True

    async def complete_step(self, plan_id, step_id, reflection=None, tools_used=None):
        self.calls.append(("complete_step", step_id))
        self.done += 1
        self.started = False


@pytest.fixture
def fake(monkeypatch):
    p = FakePlanner()
    monkeypatch.setattr(plan_runner, "_build_planner", lambda *a, **k: p)
    return p


def _config():
    return {"configurable": {"manager": MagicMock()}}


def _state(**kw):
    base = {"session_id": "s", "user_message": "do x", "llm_params": {"selected_model": "m"}, "execution_history": []}
    return {**base, **kw}


async def test_flag_on_sets_plan_ids_and_emits_agent_plan(fake):
    emitted = []
    with (
        patch.object(plan_runner, "planner_enabled", return_value=True),
        patch("chat_workflow.cot_events.emit_plan", lambda steps, **kw: emitted.append((steps, kw))),
    ):
        update = await graph_planner.create_plan(_state(), _config())
    assert update["plan_id"] == "P" and update["current_step_id"] == "id1"
    assert update["plan_progress"]["total"] == 3 and "Plan step 1 of 3" in update["plan_progress"]["block"]
    assert emitted == [(["s1", "s2", "s3"], {"session_id": "s"})]


async def test_flag_off_calls_nothing(fake):
    """Control: with the switch off the node returns at once and the planner is never touched."""
    with patch.object(plan_runner, "planner_enabled", return_value=False):
        assert await graph_planner.create_plan(_state(), _config()) == {}
    assert fake.calls == []


async def test_complete_step_is_called_after_the_inline_tool_pass(fake):
    state = _state(plan_id="P", current_step_id="id1", plan_progress={"block": "b", "done": 0, "total": 3})
    fake.started = True
    state["tool_calls"] = [{"tool": "t", "status": "success"}]
    out = await graph.execute_tools(state, _config())
    assert ("complete_step", "id1") in fake.calls and ("start_step", "id2") in fake.calls
    assert out["current_step_id"] == "id2" and out["plan_progress"]["done"] == 1


async def test_a_turn_with_no_plan_gets_no_plan_keys(fake):
    state = _state(tool_calls=[{"tool": "t", "status": "success"}])
    out = await graph.execute_tools(state, _config())
    assert "plan_id" not in out and fake.calls == []


async def test_the_current_step_reaches_the_prompt_and_the_control_does_not():
    state = _state(plan_progress={"block": "Plan step 2 of 3: s2"})
    assert graph_planner.with_plan_step("p", state).endswith("[Guidance: Plan step 2 of 3: s2]")
    assert graph_planner.with_plan_step("p", _state()) == "p"


async def test_graph_wires_create_plan_between_search_and_generation():
    g = graph.build_chat_graph()
    edges = {(a, b) for a, b in g.edges}
    assert ("perform_knowledge_search", "create_plan") in edges and ("create_plan", "generate_response") in edges
    assert ("perform_knowledge_search", "generate_response") not in edges


async def test_initialize_session_resets_plan_state():
    mgr = MagicMock()
    mgr._initialize_chat_session = AsyncMock(return_value=(MagicMock(), "t", False))
    mgr._persist_user_message = AsyncMock()
    out = await graph.initialize_session(_state(plan_id="old", current_step_id="x"), {"configurable": {"manager": mgr}})
    assert out["plan_id"] is None and out["current_step_id"] is None and out["plan_progress"] == {}
