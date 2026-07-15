# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for WorkflowRunner. Issue #6421.

Moved from enhanced_orchestration/workflow_runner_test.py (issue #10666 B3).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.workflow import ExecutionStrategy
from orchestration.types import AgentTask, WorkflowPlan
from orchestration.workflow_runner import WorkflowRunner

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
        estimated_total_duration_seconds=1.0,
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
    from orchestration.success_criteria import SuccessCriteriaEvaluator

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

        with patch("events.bus.publish_event", new_callable=AsyncMock):

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


# ---------------------------------------------------------------------------
# #7430 Phase 2 — skill_name executor consumption (ADR-006 Phase 2 of #7268)
# ---------------------------------------------------------------------------


def _skill_bound_task(task_id: str, skill_name: str = "intent_classifier", action: str = "execute") -> AgentTask:
    """Build an AgentTask with Phase-1 skill binding fields populated."""
    t = _task(task_id)
    t.skill_name = skill_name
    t.skill_action = action
    t.skill_resolution_method = "llm"
    return t


@pytest.mark.asyncio
async def test_skill_bound_task_dispatches_via_skill_not_agent():
    """A task with `skill_name` set must dispatch via SkillRegistry, NOT the agent path."""
    runner = _make_runner()

    # Skill registry mock returning an enabled skill that runs successfully
    fake_skill = MagicMock()
    fake_skill.enabled = True
    fake_skill.execute = AsyncMock(return_value={"ok": True, "output": "classified"})

    fake_registry = MagicMock()
    fake_registry.get = MagicMock(return_value=fake_skill)

    task = _skill_bound_task("t-skill", "intent_classifier", "classify")

    with patch("skills.registry.get_skill_registry", return_value=fake_registry):
        result = await runner._execute_single_agent_task(task, {})

    # Skill was dispatched
    fake_skill.execute.assert_awaited_once()
    args, _ = fake_skill.execute.call_args
    assert args[0] == "classify"  # action passed
    # The agent path was NOT taken
    runner._agent_router.get_agent_instance.assert_not_called()
    # Perf metric uses the skill: prefix, not the agent_type
    runner._perf.update.assert_called_with("skill:intent_classifier", True, pytest.approx(0.0, abs=10.0))
    # Result reflects success
    assert result.get("status") == "completed"


@pytest.mark.asyncio
async def test_unbound_task_falls_through_to_legacy_agent_path():
    """A task with `skill_name=None` must use the existing capability-based agent dispatch."""
    runner = _make_runner()

    # Agent path mock
    fake_agent = MagicMock()
    fake_agent.process_request = AsyncMock(return_value={"ok": True, "via": "agent"})
    runner._agent_router.get_agent_instance = AsyncMock(return_value=fake_agent)

    task = _task("t-legacy")
    assert task.skill_name is None  # regression guard for default

    # Patch the skill registry import — it must NOT be called for unbound tasks
    with patch("skills.registry.get_skill_registry") as mock_registry:
        result = await runner._execute_single_agent_task(task, {})
        mock_registry.assert_not_called()

    # Agent path was taken
    fake_agent.process_request.assert_awaited_once()
    runner._agent_router.get_agent_instance.assert_awaited_once()
    assert result.get("status") == "completed"


@pytest.mark.asyncio
async def test_bound_skill_missing_at_execute_time_fails_step():
    """If the bound skill was unregistered between plan and execute, fail the step.

    ADR-006 explicit choice (#7431 Q3): fail-don't-reroute. This ensures
    plans can be re-planned by upstream callers, rather than silently
    drifting between intent and execution.
    """
    runner = _make_runner()

    fake_registry = MagicMock()
    fake_registry.get = MagicMock(return_value=None)  # skill gone

    task = _skill_bound_task("t-orphan", "removed_skill")

    with patch("skills.registry.get_skill_registry", return_value=fake_registry):
        result = await runner._execute_single_agent_task(task, {})

    # Failed result, not a silent fallback to agent path
    assert result.get("status") == "failed"
    runner._agent_router.get_agent_instance.assert_not_called()


@pytest.mark.asyncio
async def test_bound_skill_disabled_at_execute_time_fails_step():
    """A skill that's registered but disabled at execute time also fails the step."""
    runner = _make_runner()

    fake_skill = MagicMock()
    fake_skill.enabled = False  # disabled mid-flight

    fake_registry = MagicMock()
    fake_registry.get = MagicMock(return_value=fake_skill)

    task = _skill_bound_task("t-disabled", "disabled_skill")

    with patch("skills.registry.get_skill_registry", return_value=fake_registry):
        result = await runner._execute_single_agent_task(task, {})

    assert result.get("status") == "failed"
    runner._agent_router.get_agent_instance.assert_not_called()


@pytest.mark.asyncio
async def test_bound_skill_default_action_is_execute():
    """If `skill_action` is None on the task, default action is 'execute' per Phase 1."""
    runner = _make_runner()

    fake_skill = MagicMock()
    fake_skill.enabled = True
    fake_skill.execute = AsyncMock(return_value={"ok": True})

    fake_registry = MagicMock()
    fake_registry.get = MagicMock(return_value=fake_skill)

    task = _task("t-default-action")
    task.skill_name = "some_skill"
    task.skill_action = None  # not set by Phase 1's `or "execute"` fallback

    with patch("skills.registry.get_skill_registry", return_value=fake_registry):
        await runner._execute_single_agent_task(task, {})

    args, _ = fake_skill.execute.call_args
    assert args[0] == "execute"


# ---------------------------------------------------------------------------
# #7431 Phase 3 — BLOCKED plan refusal + try_resume_blocked_plan
# ---------------------------------------------------------------------------


@pytest.fixture
def _fresh_pending_skills():
    from skills.pending_skills import reset_pending_skills_registry_for_tests

    reset_pending_skills_registry_for_tests()
    yield
    reset_pending_skills_registry_for_tests()


@pytest.mark.asyncio
async def test_execute_workflow_refuses_blocked_plan():
    """A plan with status='blocked' is refused — strategy handler not invoked."""
    runner = _make_runner()
    task = AgentTask(
        task_id="t1",
        agent_type="x",
        action="a",
        pending_skill_id="pending-abc-123",
    )
    plan = _plan(tasks=[task])
    plan.status = "blocked"

    with patch.object(runner, "_get_strategy_handler") as mock_handler_fn:
        mock_handler = AsyncMock()
        mock_handler.execute_by_strategy = AsyncMock(return_value={})
        mock_handler_fn.return_value = mock_handler

        result = await runner.execute_workflow(plan)

    assert result["success"] is False
    assert result["status"] == "blocked"
    assert result["reason"] == "blocked_on_skill_generation"
    assert result["pending_skill_ids"] == ["pending-abc-123"]
    mock_handler.execute_by_strategy.assert_not_called()


@pytest.mark.asyncio
async def test_execute_workflow_collects_all_pending_ids():
    runner = _make_runner()
    t1 = AgentTask(task_id="t1", pending_skill_id="pid-1")
    t2 = AgentTask(task_id="t2", pending_skill_id="pid-2")
    t3 = AgentTask(task_id="t3", agent_type="x", action="a")
    plan = _plan(tasks=[t1, t2, t3])
    plan.status = "blocked"

    result = await runner.execute_workflow(plan)
    assert result["pending_skill_ids"] == ["pid-1", "pid-2"]


@pytest.mark.asyncio
async def test_try_resume_returns_not_found_for_unknown_plan():
    runner = _make_runner()
    result = await runner.try_resume_blocked_plan("no-such-plan")
    assert result == {"resumed": False, "reason": "plan_not_found"}


@pytest.mark.asyncio
async def test_try_resume_no_op_for_non_blocked_plan():
    runner = _make_runner()
    task = AgentTask(task_id="t1", agent_type="x", action="a")
    plan = _plan(tasks=[task])  # default status='pending'
    runner.active_workflows[plan.plan_id] = plan

    result = await runner.try_resume_blocked_plan(plan.plan_id)
    assert result == {"resumed": False, "reason": "plan_not_blocked"}


@pytest.mark.asyncio
async def test_try_resume_clears_pending_re_binds_and_executes(_fresh_pending_skills):
    """Resume clears pending_skill_ids, re-binds via _bind_skill_to_task,
    transitions to pending, then executes."""
    runner = _make_runner()
    task = AgentTask(
        task_id="t1",
        agent_type="x",
        action="do",
        pending_skill_id="pid-old-123",
    )
    plan = _plan(tasks=[task])
    plan.status = "blocked"
    runner.active_workflows[plan.plan_id] = plan

    # Stub strategy_planner._bind_skill_to_task to simulate a successful
    # re-bind on the previously-blocked task
    async def fake_bind(t, td, goal):
        t.skill_name = "newly_promoted"
        t.skill_action = "execute"
        t.skill_resolution_method = "llm"

    runner._strategy_planner._bind_skill_to_task = AsyncMock(side_effect=fake_bind)

    with patch.object(runner, "_get_strategy_handler") as mock_handler_fn:
        mock_handler = AsyncMock()
        mock_handler.execute_by_strategy = AsyncMock(return_value={"t1": {"status": "completed"}})
        mock_handler_fn.return_value = mock_handler

        with patch("events.bus.publish_event", new_callable=AsyncMock):
            result = await runner.try_resume_blocked_plan(plan.plan_id)

    assert result["resumed"] is True
    assert "result" in result
    assert task.pending_skill_id is None
    assert task.skill_name == "newly_promoted"


@pytest.mark.asyncio
async def test_try_resume_stays_blocked_when_rebind_finds_no_skill(_fresh_pending_skills):
    """If re-bind doesn't resolve, plan stays blocked + pending IDs surface."""
    runner = _make_runner()
    task = AgentTask(task_id="t1", agent_type="x", action="a", pending_skill_id="pid-old")
    plan = _plan(tasks=[task])
    plan.status = "blocked"
    runner.active_workflows[plan.plan_id] = plan

    # Re-bind sets a new pending_skill_id (still no skill match)
    async def fake_bind(t, td, goal):
        t.pending_skill_id = "pid-new-456"

    runner._strategy_planner._bind_skill_to_task = AsyncMock(side_effect=fake_bind)

    result = await runner.try_resume_blocked_plan(plan.plan_id)
    assert result["resumed"] is False
    assert result["reason"] == "still_missing_skills"
    assert result["pending_skill_ids"] == ["pid-new-456"]


@pytest.mark.asyncio
async def test_try_resume_clears_pending_skills_registry_entry(_fresh_pending_skills):
    """Clearing pending_skill_id on the task also clears the binding in
    PendingSkillsRegistry so observability doesn't leak stale entries."""
    from skills.pending_skills import get_pending_skills_registry

    runner = _make_runner()
    binding = get_pending_skills_registry().register("intent", "plan-x", "task-x")
    task = AgentTask(
        task_id="task-x",
        agent_type="x",
        action="a",
        pending_skill_id=binding.pending_skill_id,
    )
    plan = _plan(tasks=[task])
    plan.plan_id = "plan-x"
    plan.status = "blocked"
    runner.active_workflows[plan.plan_id] = plan

    async def fake_bind(t, td, goal):
        t.skill_name = "good"
        t.skill_action = "execute"

    runner._strategy_planner._bind_skill_to_task = AsyncMock(side_effect=fake_bind)

    with patch.object(runner, "_get_strategy_handler") as mock_handler_fn:
        mock_handler = AsyncMock()
        mock_handler.execute_by_strategy = AsyncMock(return_value={})
        mock_handler_fn.return_value = mock_handler
        with patch("events.bus.publish_event", new_callable=AsyncMock):
            await runner.try_resume_blocked_plan(plan.plan_id)

    assert get_pending_skills_registry().get(binding.pending_skill_id) is None
