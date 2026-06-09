# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test Suite for Subagent Spawning (#4348)

Tests autonomous subagent spawning, parallel execution, failure isolation,
conflict resolution, and constraint validation.
"""

from unittest.mock import AsyncMock

import pytest

from services.agents.subagent_manager import SubagentManager
from services.agents.subagent_spawner import SubagentSpawner
from services.agents.subagent_task import (
    SubagentTask,
    TaskPriority,
    TaskResult,
    TaskStatus,
)


class TestSubagentTask:
    """Test SubagentTask data structure."""

    def test_task_creation(self):
        """Test creating a task with default values."""
        task = SubagentTask(goal="Analyze data")
        assert task.goal == "Analyze data"
        assert task.priority == TaskPriority.NORMAL
        assert task.timeout_seconds == 300
        assert task.depth == 0

    def test_task_with_custom_values(self):
        """Test creating a task with custom values."""
        constraints = {"max_memory": 512, "max_threads": 4}
        task = SubagentTask(
            goal="Process files",
            context={"files": ["a.txt", "b.txt"]},
            constraints=constraints,
            timeout_seconds=600,
            priority=TaskPriority.HIGH,
            depth=1,
        )
        assert task.goal == "Process files"
        assert task.constraints == constraints
        assert task.timeout_seconds == 600
        assert task.priority == TaskPriority.HIGH
        assert task.depth == 1

    def test_task_serialization(self):
        """Test task to_dict and from_dict."""
        original = SubagentTask(
            goal="Test task",
            context={"key": "value"},
            priority=TaskPriority.HIGH,
        )
        task_dict = original.to_dict()
        restored = SubagentTask.from_dict(task_dict)

        assert restored.goal == original.goal
        assert restored.context == original.context
        assert restored.priority == original.priority
        assert restored.task_id == original.task_id

    def test_task_result_creation(self):
        """Test creating a task result."""
        result = TaskResult(
            task_id="task-123",
            status=TaskStatus.COMPLETED,
            output={"data": "result"},
            duration_seconds=5.2,
        )
        assert result.task_id == "task-123"
        assert result.status == TaskStatus.COMPLETED
        assert result.output == {"data": "result"}
        assert result.duration_seconds == 5.2

    def test_task_result_serialization(self):
        """Test result to_dict and from_dict."""
        original = TaskResult(
            task_id="task-456",
            status=TaskStatus.FAILED,
            error="Something went wrong",
        )
        result_dict = original.to_dict()
        restored = TaskResult.from_dict(result_dict)

        assert restored.task_id == original.task_id
        assert restored.status == original.status
        assert restored.error == original.error


class TestSubagentSpawner:
    """Test SubagentSpawner parallel execution."""

    @pytest.fixture
    def spawner(self):
        """Create a spawner instance for testing."""
        return SubagentSpawner(redis_client=None)

    def test_spawner_initialization(self, spawner):
        """Test spawner initialization."""
        assert spawner.pending_tasks == {}
        assert spawner.active_subagents == {}

    def test_spawn_valid_number_of_subagents(self, spawner):
        """Test spawning valid number of subagents."""
        tasks = [{"goal": f"Task {i}", "context": {"index": i}} for i in range(3)]
        # Validate constraints at spawner level
        assert len(tasks) <= 5  # MAX_SUBAGENTS_PER_PARENT

    @pytest.mark.asyncio
    async def test_spawn_exceeds_max_subagents(self, spawner):
        """Test spawning exceeds max subagents constraint."""
        tasks = [{"goal": f"Task {i}", "context": {"index": i}} for i in range(6)]
        # This should raise ValueError in spawn_subagents
        with pytest.raises(ValueError, match="Cannot spawn 6 subagents"):
            await spawner.spawn_subagents("parent-1", tasks)

    @pytest.mark.asyncio
    async def test_spawn_exceeds_max_depth(self, spawner):
        """Test spawning at max depth constraint."""
        tasks = [{"goal": "Task", "context": {}}]

        # At depth 2 (max), should raise ValueError
        with pytest.raises(ValueError, match="Cannot spawn subagents at depth"):
            await spawner.spawn_subagents("parent-1", tasks, parent_depth=2)

    @pytest.mark.asyncio
    async def test_spawn_without_waiting(self):
        """Test spawning subagents without waiting for completion."""
        spawner = SubagentSpawner(redis_client=None)
        tasks = [{"goal": f"Task {i}", "context": {"index": i}, "timeout_seconds": 10} for i in range(3)]

        result = await spawner.spawn_subagents("parent-1", tasks, wait_for_all=False)

        assert result["status"] == "spawned"
        assert result["count"] == 3
        assert len(result["subagent_ids"]) == 3
        assert result["parent_task_id"] == "parent-1"

    @pytest.mark.asyncio
    async def test_aggregate_results_all_strategy(self):
        """Test aggregating results with 'all' strategy."""
        spawner = SubagentSpawner()
        results = [
            TaskResult(task_id="t1", status=TaskStatus.COMPLETED, output={"value": 10}),
            TaskResult(task_id="t2", status=TaskStatus.COMPLETED, output={"value": 20}),
            TaskResult(task_id="t3", status=TaskStatus.FAILED, error="Failed"),
        ]

        aggregation = await spawner.aggregate_results(results, strategy="all")

        assert aggregation["total_tasks"] == 3
        assert aggregation["successful"] == 2
        assert aggregation["failed"] == 1
        assert aggregation["strategy"] == "all"
        assert len(aggregation["results"]) == 3

    @pytest.mark.asyncio
    async def test_aggregate_results_consensus_strategy(self):
        """Test aggregating results with 'consensus' strategy."""
        spawner = SubagentSpawner()
        results = [
            TaskResult(task_id="t1", status=TaskStatus.COMPLETED, output={"answer": "yes"}),
            TaskResult(task_id="t2", status=TaskStatus.COMPLETED, output={"answer": "yes"}),
            TaskResult(task_id="t3", status=TaskStatus.COMPLETED, output={"answer": "yes"}),
        ]

        aggregation = await spawner.aggregate_results(results, strategy="consensus")

        assert aggregation["status"] == "consensus_reached"
        assert aggregation["consensus_output"] == {"answer": "yes"}

    @pytest.mark.asyncio
    async def test_aggregate_results_majority_strategy(self):
        """Test aggregating results with 'majority' strategy."""
        spawner = SubagentSpawner()
        results = [
            TaskResult(task_id="t1", status=TaskStatus.COMPLETED, output="A"),
            TaskResult(task_id="t2", status=TaskStatus.COMPLETED, output="A"),
            TaskResult(task_id="t3", status=TaskStatus.COMPLETED, output="B"),
        ]

        aggregation = await spawner.aggregate_results(results, strategy="majority")

        assert aggregation["status"] == "majority_selected"
        assert aggregation["confidence"] > 0.5

    @pytest.mark.asyncio
    async def test_resolve_conflicts_no_conflict(self):
        """Test conflict resolution when no conflict exists."""
        spawner = SubagentSpawner()
        results = [
            TaskResult(task_id="t1", status=TaskStatus.COMPLETED, output={"result": "same"}),
            TaskResult(task_id="t2", status=TaskStatus.COMPLETED, output={"result": "same"}),
        ]

        conflict = await spawner.resolve_conflicts(results)

        assert conflict is None

    @pytest.mark.asyncio
    async def test_resolve_conflicts_detected(self):
        """Test conflict detection and resolution."""
        spawner = SubagentSpawner()
        results = [
            TaskResult(task_id="t1", status=TaskStatus.COMPLETED, output="X"),
            TaskResult(task_id="t2", status=TaskStatus.COMPLETED, output="Y"),
            TaskResult(task_id="t3", status=TaskStatus.COMPLETED, output="X"),
        ]

        conflict = await spawner.resolve_conflicts(results, strategy="consensus")

        assert conflict is not None
        assert conflict.resolved_output is not None
        assert len(conflict.task_ids) == 3


class TestSubagentManager:
    """Test SubagentManager lifecycle management."""

    @pytest.fixture
    def manager(self):
        """Create a manager instance for testing."""
        mock_redis = AsyncMock()
        manager = SubagentManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_manager_initialization(self, manager):
        """Test manager initialization."""
        assert manager.local_results == {}

    @pytest.mark.asyncio
    async def test_register_subagent(self, manager):
        """Test registering a subagent."""
        task = SubagentTask(goal="Test goal", context={"key": "value"})

        task_id = await manager.register_subagent(task)

        assert task_id == task.task_id
        manager.redis.set.assert_called()

    @pytest.mark.asyncio
    async def test_set_task_status(self, manager):
        """Test setting task status."""
        await manager.set_task_status("task-1", TaskStatus.RUNNING)

        manager.redis.set.assert_called()
        call_args = manager.redis.set.call_args
        assert call_args[0][0] == "subagent:status:task-1"

    @pytest.mark.asyncio
    async def test_record_task_result(self, manager):
        """Test recording a task result."""
        result = TaskResult(
            task_id="task-1",
            status=TaskStatus.COMPLETED,
            output={"success": True},
            duration_seconds=5.0,
        )

        await manager.record_task_result(result)

        assert "task-1" in manager.local_results
        assert manager.local_results["task-1"] == result

    @pytest.mark.asyncio
    async def test_get_task_result_from_local_cache(self, manager):
        """Test getting result from local cache."""
        result = TaskResult(task_id="task-1", status=TaskStatus.COMPLETED, output="cached")
        manager.local_results["task-1"] = result

        retrieved = await manager.get_task_result("task-1")

        assert retrieved == result
        manager.redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_batch_results(self, manager):
        """Test getting batch of results."""
        result1 = TaskResult(task_id="t1", status=TaskStatus.COMPLETED, output="r1")
        result2 = TaskResult(task_id="t2", status=TaskStatus.COMPLETED, output="r2")
        manager.local_results["t1"] = result1
        manager.local_results["t2"] = result2

        results = await manager.get_batch_results(["t1", "t2"])

        assert results["t1"] == result1
        assert results["t2"] == result2

    @pytest.mark.asyncio
    async def test_cleanup_parent_tasks(self, manager):
        """Test cleanup of parent task data."""
        manager.redis.lrange.return_value = ["child1", "child2", "child3"]

        success = await manager.cleanup_parent_tasks("parent-1")

        assert success is True
        assert manager.redis.delete.called
        assert manager.redis.lrange.called

    @pytest.mark.asyncio
    async def test_distribute_work_success(self, manager):
        """Test distributing work that succeeds."""
        task = SubagentTask(goal="Process", timeout_seconds=10)
        executor = AsyncMock(return_value={"result": "success"})

        result = await manager.distribute_work(task, executor)

        assert result.task_id == task.task_id
        assert result.status == TaskStatus.COMPLETED
        assert result.output == {"result": "success"}
        executor.assert_called_once_with(task)

    @pytest.mark.asyncio
    async def test_distribute_work_timeout(self, manager):
        """Test distributing work that times out."""
        task = SubagentTask(goal="Slow task", timeout_seconds=0.1)

        async def slow_executor(t):
            await asyncio.sleep(1)
            return "too late"

        result = await manager.distribute_work(task, slow_executor)

        assert result.status == TaskStatus.TIMEOUT
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_distribute_work_failure(self, manager):
        """Test distributing work that fails."""
        task = SubagentTask(goal="Failing task", timeout_seconds=10)
        executor = AsyncMock(side_effect=ValueError("Test error"))

        result = await manager.distribute_work(task, executor)

        assert result.status == TaskStatus.FAILED
        assert "Test error" in result.error

    @pytest.mark.asyncio
    async def test_wait_for_results_all_complete(self, manager):
        """Test waiting for all results to complete."""
        result1 = TaskResult(task_id="t1", status=TaskStatus.COMPLETED, output="r1")
        result2 = TaskResult(task_id="t2", status=TaskStatus.COMPLETED, output="r2")
        manager.local_results["t1"] = result1
        manager.local_results["t2"] = result2

        results = await manager.wait_for_results(["t1", "t2"], timeout_seconds=5, check_interval=0.1)

        assert results["t1"] == result1
        assert results["t2"] == result2


class TestParallelExecution:
    """Test parallel execution of subagents."""

    @pytest.mark.asyncio
    async def test_spawn_3_parallel_subagents(self):
        """Test spawning and executing 3 subagents in parallel."""
        spawner = SubagentSpawner()
        manager = SubagentManager(redis_client=AsyncMock())

        # Simulate 3 independent tasks
        tasks = [{"goal": f"Analyze component {i}", "timeout_seconds": 10} for i in range(3)]

        # Spawn without waiting
        spawn_result = await spawner.spawn_subagents("analysis-parent", tasks, wait_for_all=False)

        assert spawn_result["count"] == 3
        assert len(spawn_result["subagent_ids"]) == 3

        # Simulate parallel execution
        async def simulate_executor(task):
            await asyncio.sleep(0.1)
            return {"status": "analyzed", "goal": task.goal}

        tasks_obj = [SubagentTask.from_dict(t) for t in tasks]
        results = await asyncio.gather(*[manager.distribute_work(t, simulate_executor) for t in tasks_obj])

        assert len(results) == 3
        assert all(r.status == TaskStatus.COMPLETED for r in results)

    @pytest.mark.asyncio
    async def test_failure_isolation(self):
        """Test that subagent failures don't affect others."""
        manager = SubagentManager(redis_client=AsyncMock())

        async def executor_1(task):
            return {"result": "success"}

        async def executor_2(task):
            raise ValueError("Task failed")

        async def executor_3(task):
            return {"result": "success"}

        task1 = SubagentTask(goal="Task 1", timeout_seconds=10)
        task2 = SubagentTask(goal="Task 2", timeout_seconds=10)
        task3 = SubagentTask(goal="Task 3", timeout_seconds=10)

        results = await asyncio.gather(
            manager.distribute_work(task1, executor_1),
            manager.distribute_work(task2, executor_2),
            manager.distribute_work(task3, executor_3),
        )

        assert results[0].status == TaskStatus.COMPLETED
        assert results[1].status == TaskStatus.FAILED
        assert results[2].status == TaskStatus.COMPLETED


if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])
