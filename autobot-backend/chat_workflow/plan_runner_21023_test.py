# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""plan_runner: depth policy, advancing from tool results, and that the legacy loop and delegation share it (#21023)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow import limits, plan_runner
from chat_workflow.manager import ChatWorkflowManager

pytestmark = pytest.mark.asyncio

_PLAN = {
    "steps": [{"step_number": i, "description": f"s{i}", "depends_on": [i - 1] if i > 1 else []} for i in (1, 2, 3)]
}


class _Redis:
    def __init__(self):
        self.d = {}

    async def set(self, k, v, ex=None):
        self.d[k] = v

    async def get(self, k):
        return self.d.get(k)


@pytest.fixture
def manager():
    m = ChatWorkflowManager.__new__(ChatWorkflowManager)
    m.redis_client = _Redis()
    return m


@pytest.fixture(autouse=True)
def _llm():
    with patch.object(plan_runner.PlannerLLMClient, "generate", AsyncMock(return_value=json.dumps(_PLAN))):
        yield


async def test_depth_policy_gives_a_delegated_run_a_shallower_plan_then_none():
    cap = limits.MAX_CONTINUATION_ITERATIONS
    assert plan_runner.steps_for_depth(0) == cap
    assert 0 < plan_runner.steps_for_depth(1) < cap
    assert plan_runner.steps_for_depth(cap) == 0  # control: deep enough that no plan is worth it


async def test_open_plan_starts_step_one_and_advance_walks_to_the_end(manager):
    t = await plan_runner.open_plan(manager, session_id="s", task="x", model="m")
    assert t.state_update()["plan_progress"]["block"].startswith("Plan step 1 of 3")
    await t.advance([{"tool": "a", "status": "pending_approval"}])  # nothing ran: no movement
    assert t.state_update()["plan_progress"]["done"] == 0
    for n in (1, 2, 3):
        await t.advance([{"tool": "a", "status": "success"}])
        assert t.state_update()["plan_progress"]["done"] == n
    assert t.state_update()["current_step_id"] is None and t.state_update()["plan_progress"]["complete"]


async def test_a_tool_error_fails_the_step_and_ends_the_plan(manager):
    t = await plan_runner.open_plan(manager, session_id="s", task="x", model="m")
    await t.advance([{"tool": "a", "status": "error", "error": "boom"}])
    assert t.state_update()["current_step_id"] is None and t.with_block("p") == "p"


async def test_a_fallback_plan_is_no_plan(manager):
    with patch.object(plan_runner.PlannerLLMClient, "generate", AsyncMock(side_effect=RuntimeError("x"))):
        assert await plan_runner.open_plan(manager, session_id="s", task="x", model="m") is None


async def test_open_for_ctx_is_a_noop_when_off_and_keyed_on_depth_when_on(manager):
    ctx = SimpleNamespace(session_id="s", message="x", selected_model="m", context={})
    with patch.object(plan_runner, "planner_enabled", return_value=False):
        assert isinstance(await plan_runner.open_for_ctx(manager, ctx), plan_runner.NoPlan)
    with patch.object(plan_runner, "planner_enabled", return_value=True):
        assert isinstance(await plan_runner.open_for_ctx(manager, ctx), plan_runner.PlanTracker)
        deep = SimpleNamespace(**{**ctx.__dict__, "context": {"delegation_depth": limits.MAX_CONTINUATION_ITERATIONS}})
        assert isinstance(await plan_runner.open_for_ctx(manager, deep), plan_runner.NoPlan)


async def test_the_legacy_loop_that_delegation_drives_plans_and_advances_through_plan_runner(manager):
    """_run_llm_iterations is the loop delegation._run_internal_subagent drives: one runner serves both."""
    history: list = []

    async def one_pass(self, http, prompt, iteration, ctx):
        assert "Plan step 1 of 3" in prompt if iteration == 1 else True
        history.append({"tool": "t", "status": "success"})
        yield ("reply", iteration < 2)

    ctx = SimpleNamespace(
        session_id="s", message="x", selected_model="m", context={}, initial_prompt="go", execution_history=history
    )
    with (
        patch.object(plan_runner, "planner_enabled", return_value=True),
        patch.object(ChatWorkflowManager, "_run_continuation_loop_iteration", one_pass),
        patch("chat_workflow.manager._emit_before_continuation", AsyncMock(return_value=True)),
        patch("chat_workflow.manager._emit_after_continuation", AsyncMock(side_effect=lambda i, r, s, c: r)),
        patch.object(ChatWorkflowManager, "_build_and_log_continuation_prompt", lambda self, c, h: "next"),
        patch.object(
            plan_runner.PlanTracker, "advance", autospec=True, side_effect=plan_runner.PlanTracker.advance
        ) as advance,
    ):
        out = [i async for i in manager._run_llm_iterations(None, ctx)]
    assert advance.call_count == 2 and out[-1][0] == ["reply", "reply"]
