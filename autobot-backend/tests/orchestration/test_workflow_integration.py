# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Integration tests for GH#7268 Phases 2 and 3.

Phase 2 — WorkflowExecutor dispatches via SkillRegistry:
- A task with ``skill_name`` set routes to ``_dispatch_via_skill`` and the
  stub skill's ``execute`` coroutine is invoked (ADR-006 Phase 2).
- Missing / disabled skills fail the step; no silent re-route to agent path
  (ADR-006 'fail-don't-reroute' policy).
- End-to-end ``execute_workflow`` with a skill-bound plan completes
  successfully.

Phase 3 — unknown capability → learning loop → plan unblocked:
- A planner that finds no winning skill builds a BLOCKED plan and attaches
  ``pending_skill_id`` to each unresolved task.
- ``try_resume_blocked_plan`` re-binds tasks once a skill is available,
  flips ``plan.status`` back to ``"pending"``, and executes the plan.
- ``BlockedPlanResumer._handle_event`` forwards a ``skill_promoted`` event
  to ``try_resume_blocked_plan`` for every BLOCKED plan in
  ``active_workflows``, and skips non-blocked plans.

No real Redis, SkillRegistry, or agent processes are required.  All external
dependencies are replaced with ``unittest.mock`` stubs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from autobot_shared.workflow import ExecutionStrategy
from orchestration.types import AgentTask, WorkflowPlan
from orchestration.workflow_planning import StrategyPlanner
from orchestration.workflow_runner import WorkflowRunner

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _stub_skill(return_value: dict | None = None) -> MagicMock:
    """Stub skill with enabled=True and an AsyncMock execute()."""
    skill = MagicMock()
    skill.enabled = True
    skill.execute = AsyncMock(return_value=return_value or {"output": "ok"})
    return skill


def _stub_registry(skill_name: str, skill: MagicMock) -> MagicMock:
    """Stub SkillRegistry whose .get() returns ``skill`` only for ``skill_name``."""
    reg = MagicMock()
    reg.get = MagicMock(side_effect=lambda n: skill if n == skill_name else None)
    return reg


def _task(
    task_id: str = "t1",
    skill_name: str | None = None,
    skill_action: str | None = None,
) -> AgentTask:
    return AgentTask(
        task_id=task_id,
        agent_type="stub_agent",
        action="run",
        skill_name=skill_name,
        skill_action=skill_action or ("execute" if skill_name else None),
    )


def _plan(tasks: list | None = None, status: str = "pending") -> WorkflowPlan:
    tasks = tasks or [_task()]
    p = WorkflowPlan(
        plan_id="plan-it-1",
        goal="test goal",
        strategy=ExecutionStrategy.SEQUENTIAL,
        tasks=tasks,
        dependencies_graph={t.task_id: [] for t in tasks},
        estimated_total_duration_seconds=1.0,
        resource_requirements={},
        success_criteria=[],
    )
    p.status = status
    return p


def _make_runner(
    planner: StrategyPlanner | None = None,
    active_workflows: dict | None = None,
) -> WorkflowRunner:
    """Construct a WorkflowRunner with fully-mocked collaborators.

    When ``planner`` is None a ``MagicMock`` stands in (sufficient for
    Phase 2 tests).  For Phase 3 tests pass a real ``StrategyPlanner`` with
    its skill router pre-configured.
    """
    if planner is None:
        planner = MagicMock()
        planner.topological_sort_tasks.side_effect = lambda tasks, deps: tasks
        planner.dependencies_met.return_value = True
        planner.group_pipeline_stages.return_value = [[]]
        planner.enhance_task_for_collaboration.side_effect = lambda t, c: t
        planner.check_success_criteria.return_value = True
        planner.summarize_results.return_value = {}

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
        strategy_planner=planner,
        performance_tracker=perf,
        active_workflows=active_workflows if active_workflows is not None else {},
        collaboration=collab,
        agent_router=agent_router,
    )


@pytest.fixture(autouse=True)
def _fresh_pending_skills():
    """Reset the PendingSkillsRegistry singleton before and after each test."""
    from skills.pending_skills import reset_pending_skills_registry_for_tests

    reset_pending_skills_registry_for_tests()
    yield
    reset_pending_skills_registry_for_tests()


# ===========================================================================
# Phase 2: WorkflowExecutor dispatches via SkillRegistry
# ===========================================================================


@pytest.mark.asyncio
async def test_dispatch_via_skill_invokes_stub_skill() -> None:
    """Phase 2: task.skill_name routes execution to the stub SkillRegistry entry.

    Verifies:
    - registry.get() called with the correct skill name
    - skill.execute() awaited with the task's ``skill_action``
    - result shape is ``{"status": "completed", ...}``
    """
    stub = _stub_skill({"classification": "positive"})
    stub_reg = _stub_registry("my_skill", stub)

    runner = _make_runner()
    task = _task("t1", skill_name="my_skill", skill_action="execute")
    task.start_execution()

    with patch("skills.registry.get_skill_registry", return_value=stub_reg):
        result = await runner._dispatch_via_skill(task, context={})

    stub_reg.get.assert_called_once_with("my_skill")
    stub.execute.assert_awaited_once()
    action_arg = stub.execute.call_args[0][0]
    assert action_arg == "execute", "skill_action must be forwarded to skill.execute()"
    assert result["status"] == "completed"
    assert result["output"] == {"classification": "positive"}


@pytest.mark.asyncio
async def test_dispatch_via_skill_raises_when_skill_not_registered() -> None:
    """Phase 2 ADR-006 'fail-don't-reroute': absent skill at execute time → RuntimeError."""
    empty_reg = MagicMock()
    empty_reg.get = MagicMock(return_value=None)

    runner = _make_runner()
    task = _task("t1", skill_name="ghost_skill")
    task.start_execution()

    with patch("skills.registry.get_skill_registry", return_value=empty_reg):
        with pytest.raises(RuntimeError, match="not registered"):
            await runner._dispatch_via_skill(task, context={})


@pytest.mark.asyncio
async def test_dispatch_via_skill_raises_when_skill_disabled() -> None:
    """Phase 2 ADR-006: disabled skill at execute time → RuntimeError (no silent reroute)."""
    stub = _stub_skill()
    stub.enabled = False
    stub_reg = _stub_registry("disabled_skill", stub)

    runner = _make_runner()
    task = _task("t1", skill_name="disabled_skill")
    task.start_execution()

    with patch("skills.registry.get_skill_registry", return_value=stub_reg):
        with pytest.raises(RuntimeError, match="disabled"):
            await runner._dispatch_via_skill(task, context={})


@pytest.mark.asyncio
async def test_execute_workflow_end_to_end_with_skill_bound_plan() -> None:
    """Phase 2 E2E: execute_workflow succeeds when every task has skill_name pre-bound.

    Simulates the post-StrategyPlanner state where Phase 1 already populated
    ``task.skill_name`` on each task.  The executor must dispatch via the stub
    SkillRegistry and return ``success=True``.
    """
    stub = _stub_skill({"answer": "42"})
    stub_reg = _stub_registry("answer_skill", stub)

    task = _task("task-1", skill_name="answer_skill", skill_action="execute")
    plan = _plan(tasks=[task])

    runner = _make_runner()

    with (
        patch("skills.registry.get_skill_registry", return_value=stub_reg),
        patch("orchestration.workflow_runner.publish_event", new_callable=AsyncMock),
    ):
        result = await runner.execute_workflow(plan)

    assert result["success"] is True, "workflow with skill-bound tasks must succeed"
    stub.execute.assert_awaited_once()


# ===========================================================================
# Phase 3: unknown capability → learning loop → plan unblocked
# ===========================================================================


@pytest.mark.asyncio
async def test_unknown_capability_produces_blocked_plan() -> None:
    """Phase 3 (strict mode): planner with no winning skill builds a BLOCKED plan.

    Verifies that ``plan.status == "blocked"`` and each task carries a
    non-None ``pending_skill_id`` when the skill_router returns
    ``{success: True, enabled_skill: None}`` (the 'no match' outcome that
    triggers Phase 3 gap-fill in strict mode).
    """
    fake_router = MagicMock()
    fake_router.execute = AsyncMock(return_value={"success": True, "enabled_skill": None})

    planner = StrategyPlanner(agent_capabilities={}, strict_gap_fill=True)
    planner._skill_router_skill = fake_router

    plan_data = {
        "strategy": "sequential",
        "tasks": [{"agent": "classifier", "action": "classify", "task": "classify intent"}],
    }
    plan = await planner.build_workflow_plan("test goal", plan_data)

    assert plan.status == "blocked", "plan must be BLOCKED when any task awaits a skill"
    assert len(plan.tasks) == 1
    task = plan.tasks[0]
    assert task.skill_name is None, "unresolved task must not have skill_name set"
    assert task.pending_skill_id is not None, "pending_skill_id must be set on unresolved task"


@pytest.mark.asyncio
async def test_try_resume_unblocks_plan_and_executes_when_skill_synthesized() -> None:
    """Phase 3 E2E: synthesized skill → try_resume re-binds tasks → plan executes.

    Simulates the sequence:
    1. Plan is BLOCKED: task has ``pending_skill_id`` but no ``skill_name``.
    2. Autonomous-skill-development registers 'intent_classifier'.
    3. ``try_resume_blocked_plan`` is called (by BlockedPlanResumer or manually).
    4. Planner re-binds the task; ``intent_classifier`` is now found.
    5. Plan flips to "pending"; ``execute_workflow`` runs to completion.
    """
    stub = _stub_skill({"intent": "buy"})
    stub_reg = _stub_registry("intent_classifier", stub)

    router_after = MagicMock()
    router_after.execute = AsyncMock(
        return_value={
            "success": True,
            "enabled_skill": "intent_classifier",
            "method": "llm",
        }
    )
    # strict_gap_fill=True so rebind triggers gap-fill path when needed; the
    # router here always returns a skill so gap-fill won't fire, but the strict
    # flag ensures the planner would fire it if rebind still finds no winner.
    planner = StrategyPlanner(agent_capabilities={}, strict_gap_fill=True)
    planner._skill_router_skill = router_after

    task = _task("task-resume")
    task.pending_skill_id = "pending-xyz"
    plan = _plan(tasks=[task], status="blocked")

    active_workflows = {plan.plan_id: plan}
    runner = _make_runner(planner=planner, active_workflows=active_workflows)

    with (
        patch("skills.registry.get_skill_registry", return_value=stub_reg),
        patch("orchestration.workflow_runner.publish_event", new_callable=AsyncMock),
    ):
        result = await runner.try_resume_blocked_plan(plan.plan_id)

    assert result["resumed"] is True, "plan must be resumed when skill is now available"
    assert plan.status != "blocked", "plan.status must flip away from 'blocked' after rebind"
    stub.execute.assert_awaited(), "skill.execute must be called during resumed execution"


@pytest.mark.asyncio
async def test_try_resume_stays_blocked_when_skill_still_unavailable() -> None:
    """Phase 3: plan stays BLOCKED when the rebind still finds no skill.

    The router continues returning ``enabled_skill: None`` — no skill has
    been generated yet.  ``try_resume_blocked_plan`` must return
    ``{"resumed": False, "reason": "still_missing_skills"}`` and leave
    ``plan.status == "blocked"``.
    """
    router_miss = MagicMock()
    router_miss.execute = AsyncMock(return_value={"success": True, "enabled_skill": None})
    planner = StrategyPlanner(agent_capabilities={}, strict_gap_fill=True)
    planner._skill_router_skill = router_miss

    task = _task("task-stuck")
    task.pending_skill_id = "pending-stuck"
    plan = _plan(tasks=[task], status="blocked")

    active_workflows = {plan.plan_id: plan}
    runner = _make_runner(planner=planner, active_workflows=active_workflows)

    result = await runner.try_resume_blocked_plan(plan.plan_id)

    assert result["resumed"] is False
    assert result["reason"] == "still_missing_skills"
    assert plan.status == "blocked", "plan must remain BLOCKED when rebind finds no skill"


@pytest.mark.asyncio
async def test_try_resume_returns_not_found_for_unknown_plan() -> None:
    """try_resume_blocked_plan returns plan_not_found for an unknown plan_id."""
    runner = _make_runner()
    result = await runner.try_resume_blocked_plan("does-not-exist")
    assert result["resumed"] is False
    assert result["reason"] == "plan_not_found"


@pytest.mark.asyncio
async def test_try_resume_no_ops_on_non_blocked_plan() -> None:
    """try_resume_blocked_plan is a no-op when the plan is not BLOCKED."""
    task = _task("t-ready")
    plan = _plan(tasks=[task], status="pending")
    active_workflows = {plan.plan_id: plan}
    runner = _make_runner(active_workflows=active_workflows)

    result = await runner.try_resume_blocked_plan(plan.plan_id)

    assert result["resumed"] is False
    assert result["reason"] == "plan_not_blocked"


@pytest.mark.asyncio
async def test_blocked_plan_resumer_handle_event_calls_try_resume() -> None:
    """Phase 3: BlockedPlanResumer._handle_event calls try_resume for every BLOCKED plan.

    When a ``skill_promoted`` message arrives on the pub-sub channel,
    BlockedPlanResumer must call ``try_resume_blocked_plan`` for each plan
    whose ``status == "blocked"``.
    """
    task = _task("t-waiting")
    task.pending_skill_id = "pending-evt"
    plan = _plan(tasks=[task], status="blocked")

    runner = _make_runner(active_workflows={plan.plan_id: plan})
    runner.try_resume_blocked_plan = AsyncMock(return_value={"resumed": True})

    from orchestration.blocked_plan_resumer import BlockedPlanResumer

    resumer = BlockedPlanResumer(runner)
    await resumer._handle_event(json.dumps({"skill_name": "new_skill"}))

    runner.try_resume_blocked_plan.assert_awaited_once_with(plan.plan_id)


@pytest.mark.asyncio
async def test_blocked_plan_resumer_skips_non_blocked_plans() -> None:
    """BlockedPlanResumer only targets plans in BLOCKED state.

    Non-blocked plans share the ``active_workflows`` dict but must not
    receive a ``try_resume_blocked_plan`` call.
    """
    task_ok = _task("t-ok")
    plan_ok = _plan(tasks=[task_ok], status="pending")

    task_blocked = _task("t-blocked")
    task_blocked.pending_skill_id = "pending-b"
    plan_blocked = _plan(tasks=[task_blocked], status="blocked")
    plan_blocked.plan_id = "plan-blocked-2"

    runner = _make_runner(
        active_workflows={
            plan_ok.plan_id: plan_ok,
            plan_blocked.plan_id: plan_blocked,
        }
    )
    runner.try_resume_blocked_plan = AsyncMock(return_value={"resumed": True})

    from orchestration.blocked_plan_resumer import BlockedPlanResumer

    resumer = BlockedPlanResumer(runner)
    await resumer._handle_event(json.dumps({"skill_name": "skill_x"}))

    runner.try_resume_blocked_plan.assert_awaited_once_with(plan_blocked.plan_id)
