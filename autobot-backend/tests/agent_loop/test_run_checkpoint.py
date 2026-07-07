# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Durable run checkpointing + resume_run for AgentLoop (GH#11175).

Covers the TaskContext snapshot round-trip, the per-iteration Redis checkpoint,
and resume_run restoring state and continuing to a terminal result.
"""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_loop.loop import AgentLoop, _run_checkpoint_key
from agent_loop.types import TaskContext

# The stubbing conftest plants a fake ``agent_loop`` package, so string-target
# patches like ``patch("agent_loop.loop.x")`` fail dot-lookup; patch the real
# module object fetched from sys.modules instead.
_loop_module = sys.modules["agent_loop.loop"]


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
    loop._iteration_count = 3
    redis_set = AsyncMock()
    with patch("autobot_shared.redis_client.redis_set", redis_set):
        await loop._checkpoint_run()
    redis_set.assert_awaited_once()
    key, payload = redis_set.await_args.args[0], redis_set.await_args.args[1]
    assert key == _run_checkpoint_key("task-abc")
    assert json.loads(payload)["iteration_count"] == 3


@pytest.mark.asyncio
async def test_checkpoint_syncs_live_iteration_counter():
    """Regression: the snapshot must record the loop's live counter, not the
    context's stale default — nothing else advances context.iteration_count."""
    loop = _loop()
    loop._current_context = TaskContext(task_id="t", description="d")  # iteration_count defaults to 0
    loop._iteration_count = 5
    redis_set = AsyncMock()
    with patch("autobot_shared.redis_client.redis_set", redis_set):
        await loop._checkpoint_run()
    assert json.loads(redis_set.await_args.args[1])["iteration_count"] == 5


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


@pytest.mark.asyncio
async def test_run_task_clears_checkpoint_on_failure():
    """A failed run must drop its checkpoint (finally path), not leave it resumable."""
    loop = _loop()
    slack = MagicMock()
    slack.post_agent_status = AsyncMock()
    slack.post_task_completion = AsyncMock()
    loop._create_task_plan = AsyncMock()
    loop._execute_main_loop = AsyncMock(side_effect=RuntimeError("boom"))
    loop._clear_run_checkpoint = AsyncMock()
    with patch.object(_loop_module, "get_slack_hook", return_value=slack):
        with pytest.raises(RuntimeError):
            await loop.run_task("do it", task_id="task-x")
    loop._clear_run_checkpoint.assert_awaited_with("task-x")
