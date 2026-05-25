# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Integration tests for GOAP adaptive replanning in WorkflowRunner (GH#7354).

Covers the AC:
  "3-step plan, second step fails, replanner picks a different third action
   that still reaches the goal."
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.workflow import ExecutionStrategy
from enhanced_orchestration.types import AgentTask, WorkflowPlan
from enhanced_orchestration.workflow_runner import WorkflowRunner
from orchestration.goap_planner import GOAPAction, GOAPPlanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runner() -> WorkflowRunner:
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
    )


def _goap_task(task_id: str, action: str, effects: list, dependencies: list = None, status: str = "pending") -> AgentTask:
    t = AgentTask(
        task_id=task_id,
        agent_type="test_agent",
        action=action,
        inputs={},
        effects=effects,
        dependencies=dependencies or [],
    )
    t.status = status
    return t


# ---------------------------------------------------------------------------
# Integration: 3-step plan, second step fails, replan succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_goap_replan_on_step_failure():
    """WorkflowRunner triggers GOAP replan when a GOAP plan step fails.

    3-step plan (research → run_tests → open_pr):
    - Step 1 (research) completes → effects: {research_done}
    - Step 2 (run_tests) fails  → triggers replanning from {research_done}
    - Replanner chooses different path (analyze_data → generate_code → open_pr_without_tests)
    """
    runner = _make_runner()

    # Build a GOAP plan whose second task will be made to fail.
    step1 = _goap_task("t1", "research", ["research_done"], status="completed")
    step2 = _goap_task("t2", "run_tests", ["tests_passed"], dependencies=["t1"], status="failed")
    step3 = _goap_task("t3", "open_pr", ["pr_opened"], dependencies=["t2"], status="pending")

    goap_plan = WorkflowPlan(
        plan_id="goap-test",
        goal="open a PR",
        tasks=[step1, step2, step3],
        strategy=ExecutionStrategy.SEQUENTIAL,
        is_goap_plan=True,
        goap_goal=["pr_opened"],
    )

    results = {
        "t1": {"status": "completed"},
        "t2": {"status": "failed", "error": "tests failed"},
    }

    # Patch execute_workflow on the recursive call so the replan "succeeds".
    replan_called_with = {}

    async def fake_execute_workflow(plan, _depth=0):
        if plan.plan_id != "goap-test":
            replan_called_with["plan_id"] = plan.plan_id
            replan_called_with["tasks"] = [t.action for t in plan.tasks]
            return {"plan_id": plan.plan_id, "success": True, "results": {}}
        raise RuntimeError("original plan failure")

    runner.execute_workflow = fake_execute_workflow  # type: ignore[assignment]

    result = await runner._handle_workflow_execution_failure(
        goap_plan, RuntimeError("step t2 failed"), results, _depth=0
    )

    assert result["success"] is True, f"Expected successful replan, got: {result}"
    assert "plan_id" in replan_called_with, "Replan was not triggered"
    replanned_tasks = replan_called_with.get("tasks", [])
    # The replanned path must start differently from the failed step (run_tests).
    # It may still use run_tests later — but must take a different first action.
    assert replanned_tasks[0] != "run_tests", (
        f"Replan should not start with the failed action; got: {replanned_tasks}"
    )
    # The replan must terminate with a step that achieves pr_opened.
    assert replanned_tasks[-1] in {"open_pr", "open_pr_without_tests"}


@pytest.mark.asyncio
async def test_capability_mapping_plan_skips_goap_replan():
    """Capability-mapping plans (is_goap_plan=False) never trigger GOAP replan."""
    runner = _make_runner()

    cap_plan = WorkflowPlan(
        plan_id="cap-test",
        goal="do something",
        tasks=[_goap_task("t1", "research", [])],
        strategy=ExecutionStrategy.SEQUENTIAL,
        is_goap_plan=False,
        goap_goal=[],
    )

    replan_calls = []

    async def spy_execute_workflow(plan, _depth=0):
        replan_calls.append(plan.plan_id)
        return {"plan_id": plan.plan_id, "success": True, "results": {}}

    runner.execute_workflow = spy_execute_workflow  # type: ignore[assignment]
    runner._try_goap_replan = AsyncMock(return_value=None)  # type: ignore[assignment]

    await runner._handle_workflow_execution_failure(cap_plan, RuntimeError("fail"), {}, _depth=0)

    runner._try_goap_replan.assert_not_called()


@pytest.mark.asyncio
async def test_goap_replan_unreachable_falls_back_to_fallback_chain():
    """When GOAP replan finds no path, the runner falls through to fallback_plans."""
    runner = _make_runner()

    # Plan with goal fact that cannot be reached from {research_done}.
    goap_plan = WorkflowPlan(
        plan_id="goap-unreachable",
        goal="impossible",
        tasks=[_goap_task("t1", "research", ["research_done"], status="completed")],
        strategy=ExecutionStrategy.SEQUENTIAL,
        is_goap_plan=True,
        goap_goal=["no_such_fact_exists_in_library"],
    )

    fallback_reached = []

    async def fake_execute_workflow(plan, _depth=0):
        if plan.plan_id == "goap-unreachable":
            raise RuntimeError("should not re-execute original")
        fallback_reached.append(plan.plan_id)
        return {"plan_id": plan.plan_id, "success": True, "results": {}}

    runner.execute_workflow = fake_execute_workflow  # type: ignore[assignment]

    fallback_plan = WorkflowPlan(
        plan_id="fallback-1",
        goal="fallback goal",
        tasks=[_goap_task("fb1", "research", [])],
        strategy=ExecutionStrategy.SEQUENTIAL,
    )
    goap_plan.fallback_plans = [fallback_plan]

    result = await runner._handle_workflow_execution_failure(
        goap_plan, RuntimeError("unreachable"), {}, _depth=0
    )

    assert result["success"] is True
    assert "fallback-1" in fallback_reached


# ---------------------------------------------------------------------------
# Unit: StrategyPlanner.build_goap_workflow_plan
# ---------------------------------------------------------------------------


def _make_strategy_planner():
    from enhanced_orchestration.workflow_planning import StrategyPlanner
    from orchestration.types import AgentCapability

    agent_caps = {
        "research_agent": {AgentCapability.RESEARCH},
        "code_agent": {AgentCapability.CODE_GENERATION},
        "test_agent": {AgentCapability.VALIDATION},
        "deploy_agent": {AgentCapability.SYSTEM_OPERATIONS},
    }
    return StrategyPlanner(agent_capabilities=agent_caps)


def test_build_goap_workflow_plan_produces_goap_plan():
    """StrategyPlanner.build_goap_workflow_plan() returns a GOAP-flagged plan."""
    planner = _make_strategy_planner()

    plan = planner.build_goap_workflow_plan(
        goal="Open a PR",
        goal_facts={"pr_opened"},
        plan_id="test-goap",
    )

    assert plan.is_goap_plan is True
    assert "pr_opened" in plan.goap_goal
    assert len(plan.tasks) > 0
    assert plan.tasks[-1].action in {"open_pr", "open_pr_without_tests"}


def test_build_goap_workflow_plan_unreachable_raises():
    """build_goap_workflow_plan() raises ValueError when goal is unreachable."""
    planner = _make_strategy_planner()

    with pytest.raises(ValueError, match="unreachable"):
        planner.build_goap_workflow_plan(
            goal="impossible",
            goal_facts={"no_such_fact_in_library"},
        )
