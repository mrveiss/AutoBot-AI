# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for ExecutionStrategyHandler. Issue #6421."""

import asyncio

import pytest

from enhanced_orchestration.execution_strategies import ExecutionStrategyHandler
from enhanced_orchestration.types import (
    AgentTask,
    ExecutionStrategy,
    WorkflowDependencies,
    WorkflowPlan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task(task_id: str, deps: list = None) -> AgentTask:
    return AgentTask(
        task_id=task_id,
        agent_type="test_agent",
        action="test",
        inputs={},
        dependencies=deps or [],
    )


def _plan(tasks, strategy=ExecutionStrategy.SEQUENTIAL, deps_graph=None) -> WorkflowPlan:
    return WorkflowPlan(
        plan_id="plan-1",
        goal="test",
        strategy=strategy,
        tasks=tasks,
        dependencies_graph=deps_graph or {},
        estimated_total_duration_seconds=1.0,
        resource_requirements={},
        success_criteria=[],
    )


def _completed(task_id: str) -> dict:
    return {"status": "completed", "output": {}, "execution_time": 0.0, "agent": "test_agent"}


def _failed(task_id: str) -> dict:
    return {"status": "failed", "error": "err", "agent": "test_agent"}


def _deps_met(task: AgentTask, results: dict) -> bool:
    return all(results.get(dep, {}).get("status") == "completed" for dep in task.dependencies)


async def _default_execute(task, ctx):
    return _completed(task.task_id)


def _make_handler(execute_fn=None, deps_met_fn=None, max_parallel=5, group_stages_fn=None):
    execute_fn = execute_fn or _default_execute
    deps_met_fn = deps_met_fn or _deps_met
    group_stages_fn = group_stages_fn or (lambda tasks, graph: [tasks])

    async def _noop_coord(channel):
        pass

    deps = WorkflowDependencies(
        execute_single_task=execute_fn,
        topological_sort_tasks=lambda tasks, graph: tasks,
        dependencies_met=deps_met_fn,
        group_pipeline_stages=group_stages_fn,
        enhance_task_for_collaboration=lambda task, channel: task,
        coordinate_collaboration=_noop_coord,
    )
    return ExecutionStrategyHandler(
        max_parallel_tasks=max_parallel,
        resource_semaphore=asyncio.Semaphore(max_parallel),
        deps=deps,
    )


# ---------------------------------------------------------------------------
# execute_sequential
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sequential_executes_all_tasks():
    tasks = [_task("t1"), _task("t2"), _task("t3")]
    executed = []

    async def execute(task, ctx):
        executed.append(task.task_id)
        return _completed(task.task_id)

    handler = _make_handler(execute_fn=execute)
    results = await handler.execute_sequential(_plan(tasks))
    assert executed == ["t1", "t2", "t3"]
    assert all(results[tid]["status"] == "completed" for tid in ["t1", "t2", "t3"])


@pytest.mark.asyncio
async def test_sequential_stops_on_required_task_failure():
    tasks = [_task("t1"), _task("t2"), _task("t3")]
    executed = []

    async def execute(task, ctx):
        executed.append(task.task_id)
        if task.task_id == "t2":
            return _failed(task.task_id)
        return _completed(task.task_id)

    handler = _make_handler(execute_fn=execute)
    results = await handler.execute_sequential(_plan(tasks))
    assert "t3" not in executed
    assert results["t2"]["status"] == "failed"


@pytest.mark.asyncio
async def test_sequential_continues_after_optional_task_failure():
    t2 = _task("t2")
    t2.metadata["optional"] = True
    tasks = [_task("t1"), t2, _task("t3")]
    executed = []

    async def execute(task, ctx):
        executed.append(task.task_id)
        if task.task_id == "t2":
            return _failed(task.task_id)
        return _completed(task.task_id)

    handler = _make_handler(execute_fn=execute)
    await handler.execute_sequential(_plan(tasks))
    assert "t3" in executed


@pytest.mark.asyncio
async def test_sequential_records_failed_result_when_dep_failed():
    """execute_sequential must record a failed result (not raise) when a dep fails (#6438).

    t1 is optional so the loop doesn't break after t1 fails; t2 depends on t1 so
    _wait_for_dependencies raises RuntimeError — must be caught and recorded, not propagated.
    """
    t1 = _task("t1")
    t1.metadata["optional"] = True
    t2 = _task("t2", deps=["t1"])
    executed = []

    async def execute(task, ctx):
        executed.append(task.task_id)
        if task.task_id == "t1":
            return _failed(task.task_id)
        return _completed(task.task_id)

    handler = _make_handler(execute_fn=execute)
    results = await handler.execute_sequential(_plan([t1, t2]))
    assert results["t1"]["status"] == "failed"
    assert results["t2"]["status"] == "failed"
    assert "t2" not in executed


@pytest.mark.asyncio
async def test_sequential_continues_when_blocked_dep_is_optional():
    """Optional task blocked by a failed dep must not stop the workflow (#6438).

    t1 optional (fails), t2 optional (dep on t1 → RuntimeError → recorded failed, skip),
    t3 required (no deps) → must still execute.
    """
    t1 = _task("t1")
    t1.metadata["optional"] = True
    t2 = _task("t2", deps=["t1"])
    t2.metadata["optional"] = True
    t3 = _task("t3")
    executed = []

    async def execute(task, ctx):
        executed.append(task.task_id)
        if task.task_id == "t1":
            return _failed(task.task_id)
        return _completed(task.task_id)

    handler = _make_handler(execute_fn=execute)
    results = await handler.execute_sequential(_plan([t1, t2, t3]))
    assert "t3" in executed
    assert results["t3"]["status"] == "completed"


# ---------------------------------------------------------------------------
# execute_pipeline stage failure (#6439)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_stops_after_required_stage_failure():
    """execute_pipeline must not run stage 2 when stage 1 has a required failure (#6439)."""
    t1 = _task("t1")
    t2 = _task("t2")
    stage1, stage2 = [t1], [t2]
    executed = []

    async def execute(task, ctx):
        executed.append(task.task_id)
        if task.task_id == "t1":
            return _failed(task.task_id)
        return _completed(task.task_id)

    handler = _make_handler(
        execute_fn=execute,
        group_stages_fn=lambda tasks, graph: [stage1, stage2],
    )
    results = await handler.execute_pipeline(_plan([t1, t2]))
    assert results["t1"]["status"] == "failed"
    assert "t2" not in executed


@pytest.mark.asyncio
async def test_pipeline_continues_when_failed_stage_task_is_optional():
    """execute_pipeline must proceed to next stage when only optional tasks fail (#6439)."""
    t1 = _task("t1")
    t1.metadata["optional"] = True
    t2 = _task("t2")
    stage1, stage2 = [t1], [t2]
    executed = []

    async def execute(task, ctx):
        executed.append(task.task_id)
        if task.task_id == "t1":
            return _failed(task.task_id)
        return _completed(task.task_id)

    handler = _make_handler(
        execute_fn=execute,
        group_stages_fn=lambda tasks, graph: [stage1, stage2],
    )
    results = await handler.execute_pipeline(_plan([t1, t2]))
    assert "t2" in executed
    assert results["t2"]["status"] == "completed"


@pytest.mark.asyncio
async def test_sequential_records_failed_result_when_task_raises():
    """execute_sequential must convert task exceptions to failed results, not propagate (#6459)."""
    t1 = _task("t1")
    t1.metadata["optional"] = True
    t2 = _task("t2")

    async def execute(task, ctx):
        if task.task_id == "t1":
            raise ValueError("boom")
        return _completed(task.task_id)

    handler = _make_handler(execute_fn=execute)
    results = await handler.execute_sequential(_plan([t1, t2]))
    assert results["t1"]["status"] == "failed"
    assert "boom" in results["t1"]["error"]
    assert results["t2"]["status"] == "completed"


@pytest.mark.asyncio
async def test_parallel_records_failed_result_when_task_raises():
    """execute_parallel must convert task exceptions to failed results, not propagate (#6459)."""
    t_ok = _task("t_ok")
    t_bad = _task("t_bad")

    async def execute(task, ctx):
        if task.task_id == "t_bad":
            raise RuntimeError("kaboom")
        return _completed(task.task_id)

    handler = _make_handler(execute_fn=execute)
    results = await handler.execute_parallel(_plan([t_ok, t_bad], ExecutionStrategy.PARALLEL))
    assert results["t_ok"]["status"] == "completed"
    assert results["t_bad"]["status"] == "failed"
    assert "kaboom" in results["t_bad"]["error"]


@pytest.mark.asyncio
async def test_collaborative_records_failed_result_when_task_raises():
    """execute_collaborative must convert task exceptions to failed results AND still clean up coordinator (#6459)."""
    cleanup_ran = False

    async def _coordinator(channel):
        nonlocal cleanup_ran
        try:
            await asyncio.sleep(9999)
        finally:
            cleanup_ran = True

    async def execute(task, ctx):
        raise ValueError("collab boom")

    deps = WorkflowDependencies(
        execute_single_task=execute,
        topological_sort_tasks=lambda tasks, graph: tasks,
        dependencies_met=lambda task, results: True,
        group_pipeline_stages=lambda tasks, graph: [tasks],
        enhance_task_for_collaboration=lambda task, channel: task,
        coordinate_collaboration=_coordinator,
    )
    handler = ExecutionStrategyHandler(
        max_parallel_tasks=5,
        resource_semaphore=asyncio.Semaphore(5),
        deps=deps,
    )
    results = await handler.execute_collaborative(_plan([_task("t1")], ExecutionStrategy.COLLABORATIVE))
    assert results["t1"]["status"] == "failed"
    assert "collab boom" in results["t1"]["error"]
    assert cleanup_ran


@pytest.mark.asyncio
async def test_adaptive_records_failed_result_when_sequential_step_raises():
    """execute_adaptive (via _execute_sequential_step) must convert task exceptions to failed results (#6459)."""
    t_bad = _task("t_bad")

    async def execute(task, ctx):
        raise RuntimeError("adaptive boom")

    handler = _make_handler(execute_fn=execute)
    results = await handler.execute_adaptive(_plan([t_bad], ExecutionStrategy.ADAPTIVE))
    assert results["t_bad"]["status"] == "failed"
    assert "adaptive boom" in results["t_bad"]["error"]


@pytest.mark.asyncio
async def test_safe_execute_propagates_cancelled_error():
    """_safe_execute must NOT swallow CancelledError — cooperative cancellation must still work (#6459)."""

    async def execute(task, ctx):
        raise asyncio.CancelledError()

    handler = _make_handler(execute_fn=execute)
    with pytest.raises(asyncio.CancelledError):
        await handler._safe_execute(_task("t1"), {})


@pytest.mark.asyncio
async def test_pipeline_records_failed_result_when_task_raises():
    """execute_pipeline must record a failed result when _execute_single_task raises (#6449)."""
    t1 = _task("t1")
    t2 = _task("t2")
    stage1, stage2 = [t1], [t2]
    executed = []

    async def execute(task, ctx):
        executed.append(task.task_id)
        if task.task_id == "t1":
            raise ValueError("task exploded")
        return _completed(task.task_id)

    handler = _make_handler(
        execute_fn=execute,
        group_stages_fn=lambda tasks, graph: [stage1, stage2],
    )
    results = await handler.execute_pipeline(_plan([t1, t2]))
    assert results["t1"]["status"] == "failed"
    assert "t2" not in executed


@pytest.mark.asyncio
async def test_parallel_batch_records_failed_result_when_task_raises():
    """_execute_parallel_batch must record a failed result when _execute_single_task raises (#6449)."""
    t_ok = _task("t_ok")
    t_bad = _task("t_bad")

    async def execute(task, ctx):
        if task.task_id == "t_bad":
            raise RuntimeError("boom")
        return _completed(task.task_id)

    handler = _make_handler(execute_fn=execute)
    pending = [t_ok, t_bad]
    results = {}
    c, f = await handler._execute_parallel_batch(pending, results)
    assert results["t_ok"]["status"] == "completed"
    assert results["t_bad"]["status"] == "failed"
    assert c == 1 and f == 1
    assert not pending


@pytest.mark.asyncio
async def test_wait_for_dependencies_raises_on_non_failed_terminal_status():
    """_wait_for_dependencies must raise on any non-completed terminal status, not only 'failed' (#6454)."""
    t1 = _task("t1", deps=["dep"])
    results = {"dep": {"status": "cancelled"}}

    handler = _make_handler()
    with pytest.raises(RuntimeError, match="terminal"):
        await handler._wait_for_dependencies(t1, results)


# ---------------------------------------------------------------------------
# execute_parallel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parallel_executes_independent_tasks():
    tasks = [_task("t1"), _task("t2"), _task("t3")]
    executed = []

    async def execute(task, ctx):
        executed.append(task.task_id)
        return _completed(task.task_id)

    handler = _make_handler(execute_fn=execute)
    results = await handler.execute_parallel(_plan(tasks, ExecutionStrategy.PARALLEL))
    assert set(executed) == {"t1", "t2", "t3"}
    assert all(results[tid]["status"] == "completed" for tid in ["t1", "t2", "t3"])


@pytest.mark.asyncio
async def test_parallel_deadlock_detection(caplog):
    """Tasks whose dependencies can never be satisfied must fail, not loop (#6420)."""
    t1 = _task("t1", deps=["t_missing"])

    async def execute(task, ctx):
        return _completed(task.task_id)  # pragma: no cover

    handler = _make_handler(execute_fn=execute)
    results = await handler.execute_parallel(_plan([t1], ExecutionStrategy.PARALLEL))
    assert results["t1"]["status"] == "failed"
    assert "deadlock" in results["t1"]["error"].lower()


@pytest.mark.asyncio
async def test_parallel_respects_max_parallel_tasks():
    tasks = [_task(f"t{i}") for i in range(10)]
    concurrency_peak = 0
    active = 0

    async def execute(task, ctx):
        nonlocal concurrency_peak, active
        active += 1
        concurrency_peak = max(concurrency_peak, active)
        await asyncio.sleep(0)
        active -= 1
        return _completed(task.task_id)

    handler = _make_handler(execute_fn=execute, max_parallel=3)
    await handler.execute_parallel(_plan(tasks, ExecutionStrategy.PARALLEL))
    assert concurrency_peak <= 3


# ---------------------------------------------------------------------------
# execute_adaptive — strategy switching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adaptive_switches_to_sequential_on_high_failure():
    tasks = [_task(f"t{i}") for i in range(4)]
    call_count = 0

    async def execute(task, ctx):
        nonlocal call_count
        call_count += 1
        return _failed(task.task_id)

    handler = _make_handler(execute_fn=execute)
    results = await handler.execute_adaptive(_plan(tasks, ExecutionStrategy.ADAPTIVE))
    assert all(results[t.task_id]["status"] == "failed" for t in tasks)


@pytest.mark.asyncio
async def test_adaptive_deadlock_detection():
    """execute_adaptive must not loop forever when dependencies can never be met (#6429)."""
    t1 = _task("t1", deps=["t_missing"])

    handler = _make_handler()
    results = await handler.execute_adaptive(_plan([t1], ExecutionStrategy.ADAPTIVE))
    assert results["t1"]["status"] == "failed"
    assert "deadlock" in results["t1"]["error"].lower()


# ---------------------------------------------------------------------------
# _execute_parallel_batch zip/filter fix (#6430)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parallel_batch_skips_tasks_with_unmet_deps():
    """Tasks with unmet deps must not be removed from pending or get wrong results (#6430)."""
    t_ready = _task("t_ready")
    t_blocked = _task("t_blocked", deps=["t_missing"])
    executed = []

    async def execute(task, ctx):
        executed.append(task.task_id)
        return _completed(task.task_id)

    handler = _make_handler(execute_fn=execute)
    pending = [t_ready, t_blocked]
    results = {}
    await handler._execute_parallel_batch(pending, results)

    assert "t_ready" in executed
    assert "t_blocked" not in executed
    assert t_blocked in pending  # blocked task stays in pending
    assert results.get("t_ready", {}).get("status") == "completed"
    assert "t_blocked" not in results


# ---------------------------------------------------------------------------
# execute_collaborative coordinator cleanup (#6431)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collaborative_coordinator_awaited_on_cancel():
    """coordinator_task must be awaited after cancel so finally/unsubscribe runs (#6431)."""
    cleanup_ran = False

    async def _coordinator(channel):
        nonlocal cleanup_ran
        try:
            await asyncio.sleep(9999)
        finally:
            cleanup_ran = True

    async def execute(task, ctx):
        return _completed(task.task_id)

    deps = WorkflowDependencies(
        execute_single_task=execute,
        topological_sort_tasks=lambda tasks, graph: tasks,
        dependencies_met=lambda task, results: True,
        group_pipeline_stages=lambda tasks, graph: [tasks],
        enhance_task_for_collaboration=lambda task, channel: task,
        coordinate_collaboration=_coordinator,
    )
    handler = ExecutionStrategyHandler(
        max_parallel_tasks=5,
        resource_semaphore=asyncio.Semaphore(5),
        deps=deps,
    )
    plan = _plan([_task("t1")], ExecutionStrategy.COLLABORATIVE)
    await handler.execute_collaborative(plan)
    assert cleanup_ran, "coordinator finally block must run before execute_collaborative returns"


# ---------------------------------------------------------------------------
# WorkflowDependencies injection
# ---------------------------------------------------------------------------


def test_workflow_dependencies_fields_wired_correctly():
    """Ensure all 6 callables are accessible via named deps fields."""
    sentinel = object()
    deps = WorkflowDependencies(
        execute_single_task=sentinel,
        topological_sort_tasks=sentinel,
        dependencies_met=sentinel,
        group_pipeline_stages=sentinel,
        enhance_task_for_collaboration=sentinel,
        coordinate_collaboration=sentinel,
    )
    handler = ExecutionStrategyHandler(
        max_parallel_tasks=1,
        resource_semaphore=asyncio.Semaphore(1),
        deps=deps,
    )
    assert handler._execute_single_task is sentinel
    assert handler._topological_sort_tasks is sentinel
    assert handler._dependencies_met is sentinel
    assert handler._group_pipeline_stages is sentinel
    assert handler._enhance_task_for_collaboration is sentinel
    assert handler._coordinate_collaboration is sentinel
