# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLMPlannerModule: create / start / complete / fail, the Redis store and the fallback flag (#21023)."""

from __future__ import annotations

import json

import pytest

from planner import ExecutionPlan, LLMPlannerModule, PlanStatus, PlanStepStatus
from planner.planner import PlannerConfig

pytestmark = pytest.mark.asyncio

_PLAN = {
    "task_description": "t",
    "steps": [
        {"step_number": 1, "description": "first", "depends_on": []},
        {"step_number": 2, "description": "second", "depends_on": [1]},
        {"step_number": 3, "description": "third", "depends_on": [2]},
    ],
}


class _Llm:
    def __init__(self, reply):
        self.reply = reply

    async def generate(self, prompt, temperature):
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class _Redis:
    def __init__(self):
        self.store = {}
        self.sets = []

    async def set(self, key, value, ex=None):
        self.store[key] = value
        self.sets.append((key, ex))

    async def get(self, key):
        return self.store.get(key)


def _planner(reply=None, redis=None, max_steps=20):
    reply = json.dumps(_PLAN) if reply is None else reply
    return LLMPlannerModule(_Llm(reply), None, redis_client=redis, config=PlannerConfig(max_steps_per_plan=max_steps))


async def test_create_plan_parses_steps_and_is_not_flagged_fallback():
    plan = await _planner().create_plan("do it")
    assert [s.description for s in plan.steps] == ["first", "second", "third"]
    assert plan.status is PlanStatus.READY and plan.metadata["fallback"] is False


async def test_failing_llm_gives_the_canned_plan_flagged_fallback():
    plan = await _planner(RuntimeError("down")).create_plan("do it")
    assert plan.metadata["fallback"] is True and plan.total_steps == 2


async def test_unparseable_reply_is_flagged_fallback():
    assert (await _planner("not json").create_plan("x")).metadata["fallback"] is True


async def test_steps_are_capped_at_the_configured_maximum():
    plan = await _planner(max_steps=2).create_plan("x")
    assert plan.total_steps == 2


async def test_step_lifecycle_runs_to_complete():
    p = _planner()
    plan = await p.create_plan("x")
    for _ in range(3):
        step = plan.get_next_executable_steps()[0]
        await p.start_step(plan.plan_id, step.step_id)
        assert plan.get_current_step() is step
        await p.complete_step(plan.plan_id, step.step_id, tools_used=["t"])
    assert plan.is_complete() and plan.status is PlanStatus.COMPLETED


async def test_fail_step_blocks_dependents_and_stops_the_plan():
    p = _planner()
    plan = await p.create_plan("x")
    first = plan.steps[0]
    await p.start_step(plan.plan_id, first.step_id)
    await p.fail_step(plan.plan_id, first.step_id, "boom")
    assert first.status is PlanStepStatus.FAILED and plan.status is PlanStatus.FAILED
    assert plan.steps[1].status is PlanStepStatus.BLOCKED and plan.get_next_executable_steps() == []
    assert not plan.is_complete()


async def test_plan_body_is_stored_in_redis_and_round_trips_metadata():
    redis = _Redis()
    p = _planner(redis=redis)
    plan = await p.create_plan("x")
    key = f"autobot:plans:{plan.plan_id}"
    assert redis.sets[0][0] == key and redis.sets[0][1] == p.config.plan_ttl_seconds
    fresh = _planner(redis=redis)  # a different instance reads it back from Redis, not from memory
    loaded = await fresh.get_plan(plan.plan_id)
    assert isinstance(loaded, ExecutionPlan) and loaded.total_steps == 3 and loaded.metadata == {"fallback": False}
