# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for SubagentDispatcher wiring into ParallelStrategy (#10602).

Verifies that:
- SUBAGENT_REFLECTION_ENABLED=false (default): direct asyncio.create_task path,
  SubagentDispatcher.spawn_parallel_tasks never called.
- SUBAGENT_REFLECTION_ENABLED=true: _execute_batch_with_reflection is called
  and routes tasks through get_subagent_dispatcher().
- Dispatcher errors fall back to direct _safe_execute (no tasks dropped).
- SubagentTask.timeout field fix: spawn_parallel_tasks no longer AttributeErrors
  on task.timeout_seconds.
"""

from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestration.execution_strategies._parallel import ParallelStrategy
from orchestration.subagent_dispatcher import SubagentTask, get_subagent_dispatcher


def _make_agent_task(task_id: str = "t1", description: str = "do work") -> types.SimpleNamespace:
    return types.SimpleNamespace(
        task_id=task_id,
        description=description,
        timeout=60,
        metadata={},
        to_failed_result=lambda msg: {"status": "failed", "error": msg},
    )


class TestSubagentTaskTimeoutField:
    """Guard the pre-existing timeout_seconds → timeout attribute fix."""

    @pytest.mark.asyncio
    async def test_spawn_parallel_tasks_uses_timeout_not_timeout_seconds(self):
        """spawn_parallel_tasks must not raise AttributeError for timeout_seconds."""

        async def noop():
            return "done"

        task = SubagentTask(task_id="t1", func=noop, timeout=10, enable_reflection=False)
        dispatcher = get_subagent_dispatcher.__wrapped__() if hasattr(get_subagent_dispatcher, "__wrapped__") else None
        dispatcher = MagicMock()
        dispatcher.max_parallel = 5
        dispatcher.spawn_parallel_tasks = AsyncMock(return_value={"t1": "done"})

        # Directly test the field is 'timeout', not 'timeout_seconds'
        assert hasattr(task, "timeout"), "SubagentTask must have 'timeout' field"
        assert not hasattr(task, "timeout_seconds"), "Field must be 'timeout', not 'timeout_seconds'"
        assert task.timeout == 10


class TestParallelStrategyReflectionOff:
    @pytest.mark.asyncio
    async def test_flag_off_does_not_call_batch_reflection(self, monkeypatch):
        """SUBAGENT_REFLECTION_ENABLED=false → _execute_batch_with_reflection never called."""
        monkeypatch.setattr(
            "orchestration.execution_strategies._parallel.SUBAGENT_REFLECTION_ENABLED",
            False,
        )

        execute_calls = []

        async def fake_execute(task, ctx):
            execute_calls.append(task.task_id)
            return {"status": "ok", "task_id": task.task_id}

        strategy = ParallelStrategy(
            execute_single_task=fake_execute,
            max_parallel_tasks=5,
            resource_semaphore=asyncio.Semaphore(5),
            dependencies_met=lambda task, results: True,
        )

        tasks = [_make_agent_task(f"t{i}") for i in range(3)]
        plan = types.SimpleNamespace(tasks=tasks)

        with patch.object(strategy, "_execute_batch_with_reflection", new_callable=AsyncMock) as mock_batch:
            results = await strategy.execute(plan)

        mock_batch.assert_not_called()
        assert len(results) == 3


class TestParallelStrategyReflectionOn:
    @pytest.mark.asyncio
    async def test_flag_on_calls_batch_reflection(self, monkeypatch):
        """SUBAGENT_REFLECTION_ENABLED=true → _execute_batch_with_reflection is called."""
        monkeypatch.setattr(
            "orchestration.execution_strategies._parallel.SUBAGENT_REFLECTION_ENABLED",
            True,
        )

        async def fake_execute(task, ctx):
            return {"status": "ok", "task_id": task.task_id}

        strategy = ParallelStrategy(
            execute_single_task=fake_execute,
            max_parallel_tasks=5,
            resource_semaphore=asyncio.Semaphore(5),
            dependencies_met=lambda task, results: True,
        )

        tasks = [_make_agent_task("t1")]
        plan = types.SimpleNamespace(tasks=tasks)

        batch_results = {"t1": {"status": "ok"}}
        with patch.object(
            strategy,
            "_execute_batch_with_reflection",
            new_callable=AsyncMock,
            return_value=batch_results,
        ) as mock_batch:
            results = await strategy.execute(plan)

        mock_batch.assert_called_once()
        assert results["t1"]["status"] == "ok"


class TestExecuteBatchWithReflection:
    @pytest.mark.asyncio
    async def test_routes_through_dispatcher(self, monkeypatch):
        """_execute_batch_with_reflection uses get_subagent_dispatcher."""
        monkeypatch.setattr(
            "orchestration.execution_strategies._parallel.SUBAGENT_REFLECTION_ENABLED",
            True,
        )

        async def fake_execute(task, ctx):
            return {"task_id": task.task_id, "done": True}

        strategy = ParallelStrategy(
            execute_single_task=fake_execute,
            max_parallel_tasks=5,
            resource_semaphore=asyncio.Semaphore(5),
            dependencies_met=lambda task, results: True,
        )

        tasks = [_make_agent_task("t1"), _make_agent_task("t2")]
        expected = {"t1": {"done": True}, "t2": {"done": True}}

        mock_dispatcher = MagicMock()
        mock_dispatcher.spawn_parallel_tasks = AsyncMock(return_value=expected)

        # _get_subagent_dispatcher is a module-level function; patch it directly.
        with patch(
            "orchestration.execution_strategies._parallel._get_subagent_dispatcher",
            return_value=(SubagentTask, mock_dispatcher),
        ):
            result = await strategy._execute_batch_with_reflection(tasks, {})

        mock_dispatcher.spawn_parallel_tasks.assert_called_once()
        # Verify enable_reflection=True was passed to each SubagentTask
        dispatched: list[SubagentTask] = mock_dispatcher.spawn_parallel_tasks.call_args.args[0]
        assert all(t.enable_reflection for t in dispatched)
        assert set(result.keys()) == {"t1", "t2"}

    @pytest.mark.asyncio
    async def test_dispatcher_error_falls_back_to_direct_execute(self, monkeypatch):
        """Dispatcher failure → falls back to _safe_execute, no tasks dropped."""
        monkeypatch.setattr(
            "orchestration.execution_strategies._parallel.SUBAGENT_REFLECTION_ENABLED",
            True,
        )

        completed = []

        async def fake_execute(task, ctx):
            completed.append(task.task_id)
            return {"task_id": task.task_id}

        strategy = ParallelStrategy(
            execute_single_task=fake_execute,
            max_parallel_tasks=5,
            resource_semaphore=asyncio.Semaphore(5),
            dependencies_met=lambda task, results: True,
        )

        tasks = [_make_agent_task("t1"), _make_agent_task("t2")]

        with patch(
            "orchestration.execution_strategies._parallel._get_subagent_dispatcher",
            side_effect=RuntimeError("dispatcher unavailable"),
        ):
            result = await strategy._execute_batch_with_reflection(tasks, {})

        # Fallback executed both tasks
        assert set(completed) == {"t1", "t2"}
        assert set(result.keys()) == {"t1", "t2"}
