# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for WorkflowRunner. Issue #6421."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_orchestration.types import (
    AgentTask,
    ExecutionStrategy,
    WorkflowPlan,
)
from enhanced_orchestration.workflow_runner import WorkflowRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task(task_id: str) -> AgentTask:
    return AgentTask(
        task_id=task_id,
        agent_type="test_agent",
        action="act",
        inputs={},
    )


def _plan(tasks=None, strategy=ExecutionStrategy.SEQUENTIAL) -> WorkflowPlan:
    tasks = tasks or [_task("t1")]
    return WorkflowPlan(
        plan_id="plan-test",
        goal="test goal",
        strategy=strategy,
        tasks=tasks,
        dependencies_graph={},
        estimated_duration=1.0,
        resource_requirements={},
        success_criteria=[],
    )


def _make_runner(criteria_evaluator=None):
    strategy_planner = MagicMock()
    strategy_planner.topological_sort_tasks.return_value = []
    strategy_planner.dependencies_met.return_value = True
    strategy_planner.group_pipeline_stages.return_value = [[]]
    strategy_planner.enhance_task_for_collaboration.side_effect = lambda t, c: t
    strategy_planner.check_success_criteria.return_value = True
    strategy_planner.summarize_results.return_value = {}

    perf = MagicMock()
    perf.update = MagicMock()
    perf.update_from_plan = MagicMock()
    perf.report = MagicMock(return_value={})

    agent_router = AsyncMock()
    agent_router.get_agent_recommendations = AsyncMock(return_value=[])
    agent_router.calculate_capability_coverage.return_value = {}

    collab = AsyncMock()
    collab.coordinate_collaboration = AsyncMock()

    return WorkflowRunner(
        strategy_planner=strategy_planner,
        performance_tracker=perf,
        active_workflows={},
        collaboration=collab,
        agent_router=agent_router,
        criteria_evaluator=criteria_evaluator,
    )


# ---------------------------------------------------------------------------
# criteria_evaluator injection (#6402)
# ---------------------------------------------------------------------------


def test_default_criteria_evaluator_created_when_none():
    from enhanced_orchestration.success_criteria import SuccessCriteriaEvaluator
    runner = _make_runner()
    assert isinstance(runner._criteria_evaluator, SuccessCriteriaEvaluator)


def test_injected_criteria_evaluator_is_stored():
    mock_evaluator = MagicMock()
    runner = _make_runner(criteria_evaluator=mock_evaluator)
    assert runner._criteria_evaluator is mock_evaluator


@pytest.mark.asyncio
async def test_evaluate_workflow_criteria_uses_injected_evaluator():
    eval_result = MagicMock()
    eval_result.to_dict.return_value = {"overall": "full", "score": 1.0, "results": []}
    mock_evaluator = AsyncMock()
    mock_evaluator.evaluate = AsyncMock(return_value=eval_result)

    runner = _make_runner(criteria_evaluator=mock_evaluator)
    plan = _plan()
    plan.structured_criteria = [MagicMock()]

    result = await runner._evaluate_workflow_criteria(plan, {})
    mock_evaluator.evaluate.assert_awaited_once()
    assert result["overall"] == "full"


@pytest.mark.asyncio
async def test_evaluate_workflow_criteria_binary_fallback_when_no_structured():
    runner = _make_runner()
    runner._strategy_planner.check_success_criteria.return_value = True

    plan = _plan()
    plan.structured_criteria = []
    result = await runner._evaluate_workflow_criteria(plan, {})
    assert result["overall"] == "full"
    assert result["score"] == 1.0


# ---------------------------------------------------------------------------
# fallback depth cap (#5058)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_depth_capped_at_5():
    runner = _make_runner()

    with patch.object(runner, "_get_strategy_handler") as mock_handler_fn:
        mock_handler = AsyncMock()
        mock_handler.execute_by_strategy = AsyncMock(side_effect=RuntimeError("always fails"))
        mock_handler_fn.return_value = mock_handler

        with patch("enhanced_orchestration.workflow_runner._get_event_manager") as mock_em:
            mock_em.return_value.publish = AsyncMock()

            root_plan = _plan()
            # Build a chain of 6 fallbacks (depth 0-5 = 6 levels total)
            fallback = _plan()
            fallback.fallback_plans = []
            root_plan.fallback_plans = [fallback]

            result = await runner.execute_workflow(root_plan, _depth=5)

    assert result["success"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# get_performance_report
# ---------------------------------------------------------------------------


def test_get_performance_report_shape():
    runner = _make_runner()
    runner._perf.report.return_value = {"agent_a": {"total": 1}}
    runner._agent_router.calculate_capability_coverage.return_value = {"cap_x": 0.9}
    runner.active_workflows["w1"] = MagicMock()

    report = runner.get_performance_report()
    assert "agent_performance" in report
    assert report["active_workflows"] == 1
    assert "capabilities_coverage" in report
