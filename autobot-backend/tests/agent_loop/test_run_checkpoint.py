# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Durable run checkpointing + resume_run for AgentLoop (GH#11175).

Covers the TaskContext snapshot round-trip, the per-iteration Redis checkpoint,
and resume_run restoring state and continuing to a terminal result.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_loop.loop import AgentLoop, _run_checkpoint_key
from agent_loop.types import TaskContext


def _ctx() -> TaskContext:
    ctx = TaskContext(task_id="task-abc", description="do the thing")
    ctx.iteration_count = 3
    ctx.tools_executed = ["read_file", "web_search"]
    ctx.errors = ["boom"]
    ctx.user_messages = ["hi"]
    ctx.plan_id = "plan-1"
    ctx.current_step_id = "step-2"
    ctx.metadata = {"k": "v"}
    ctx.tool_call_hashes = {"h1": 2}
    return ctx


def _loop() -> AgentLoop:
    return AgentLoop(event_stream=MagicMock())


# --- snapshot round-trip ---------------------------------------------------


def test_snapshot_roundtrip_preserves_durable_core():
    restored = TaskContext.from_snapshot(_ctx().to_snapshot())
    assert restored.task_id == "task-abc"
    assert restored.description == "do the thing"
    assert restored.iteration_count == 3
    assert restored.tools_executed == ["read_file", "web_search"]
    assert restored.errors == ["boom"]
    assert restored.user_messages == ["hi"]
    assert restored.plan_id == "plan-1"
    assert restored.current_step_id == "step-2"
    assert restored.metadata == {"k": "v"}
    assert restored.tool_call_hashes == {"h1": 2}


def test_from_snapshot_rejects_incompatible_version():
    bad = _ctx().to_snapshot()
    bad["version"] = 999
    with pytest.raises(ValueError):
        TaskContext.from_snapshot(bad)


# --- checkpoint persistence ------------------------------------------------


@pytest.mark.asyncio
async def test_checkpoint_run_writes_snapshot_to_redis():
    loop = _loop()
    loop._current_context = _ctx()
    redis_set = AsyncMock()
    with patch("autobot_shared.redis_client.redis_set", redis_set):
        await loop._checkpoint_run()
    redis_set.assert_awaited_once()
    key, payload = redis_set.await_args.args[0], redis_set.await_args.args[1]
    assert key == _run_checkpoint_key("task-abc")
    assert json.loads(payload)["iteration_count"] == 3


@pytest.mark.asyncio
async def test_checkpoint_run_noop_without_context():
    loop = _loop()
    loop._current_context = None
    redis_set = AsyncMock()
    with patch("autobot_shared.redis_client.redis_set", redis_set):
        await loop._checkpoint_run()
    redis_set.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkpoint_failure_is_swallowed():
    loop = _loop()
    loop._current_context = _ctx()
    with patch("autobot_shared.redis_client.redis_set", AsyncMock(side_effect=RuntimeError("redis down"))):
        await loop._checkpoint_run()  # must not raise


# --- resume ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_run_restores_context_and_finalizes():
    loop = _loop()
    snapshot = _ctx().to_snapshot()
    with patch.object(AgentLoop, "load_run_snapshot", AsyncMock(return_value=snapshot)):
        loop._execute_main_loop = AsyncMock(return_value=[])
        loop._finalize_task = AsyncMock(return_value={"status": "completed"})
        loop._clear_run_checkpoint = AsyncMock()
        result = await loop.resume_run("task-abc")

    assert result == {"status": "completed"}
    assert loop._current_context.task_id == "task-abc"
    assert loop._iteration_count == 3
    loop._finalize_task.assert_awaited_once()
    loop._clear_run_checkpoint.assert_awaited_once_with("task-abc")


@pytest.mark.asyncio
async def test_resume_run_raises_when_no_checkpoint():
    loop = _loop()
    with patch.object(AgentLoop, "load_run_snapshot", AsyncMock(return_value=None)):
        with pytest.raises(ValueError):
            await loop.resume_run("missing")
