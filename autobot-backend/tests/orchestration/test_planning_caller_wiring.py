# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Regression cover for the callers of the orchestrator's planning API (#13730).

Every caller of ``plan_workflow_steps`` / ``classify_request_complexity`` bound
the coroutine without awaiting it and then read ``step.id`` /
``step.user_approval_required`` — names the canonical ``WorkflowTask`` does not
define. Nothing in the suite noticed, because the only caller-level test
asserted nothing and the live caller swallowed the TypeError into ``return
None``.

These tests drive each caller with a **real** ``Orchestrator``, so a regression
to either failure mode (missing await, or a retired field name) fails here
rather than silently returning nothing in production.
"""

from unittest.mock import AsyncMock

import pytest

from orchestrator import Orchestrator, TaskComplexity


@pytest.fixture
def orchestrator():
    """A real Orchestrator — the point is to exercise the true task contract."""
    return Orchestrator()


async def test_plan_workflow_steps_with_agents_returns_assigned_steps(orchestrator):
    """The planner awaits the plan and projects canonical fields into its dicts."""
    from orchestration.workflow_planner import WorkflowPlanner

    planner = WorkflowPlanner(
        base_orchestrator=orchestrator,
        agent_registry={},
        find_best_agent_callback=lambda **kwargs: "test-agent",
    )
    # Trajectory lookup is advisory (GH#7357) and not under test here.
    planner._annotate_context_with_trajectories = AsyncMock(return_value=None)

    steps = await planner.plan_workflow_steps_with_agents("install docker", TaskComplexity.COMPLEX, {})

    assert len(steps) == 3, f"expected the COMPLEX plan to survive agent assignment, got {steps}"
    assert [step["id"] for step in steps] == ["step_1", "step_2", "step_3"]
    assert all(step["assigned_agent"] == "test-agent" for step in steps)
    assert all(step["status"] == "planned" for step in steps)
    # step_2 requires approval in the COMPLEX plan; the projection must carry it.
    assert [step["user_approval_required"] for step in steps] == [False, True, False]


async def test_get_plan_summary_returns_a_populated_summary(orchestrator):
    """get_plan_summary was sync while the API it calls is async (#13730)."""
    from orchestration.workflow_planner import WorkflowPlanner

    planner = WorkflowPlanner(
        base_orchestrator=orchestrator,
        agent_registry={},
        find_best_agent_callback=lambda **kwargs: None,
    )

    summary = await planner.get_plan_summary("install docker")

    assert summary["request"] == "install docker"
    assert summary["complexity"] == TaskComplexity.COMPLEX.value
    assert summary["total_steps"] == len(summary["steps"]) > 0
    assert [step["id"] for step in summary["steps"]] == ["step_1", "step_2", "step_3"]
    assert all(isinstance(step["requires_approval"], bool) for step in summary["steps"])


async def test_create_workflow_from_chat_request_builds_steps(orchestrator):
    """The live HTTP path: a chat request must yield a workflow, not None."""
    from services.workflow_automation.manager import WorkflowAutomationManager

    # __init__ wires messenger/executor/controller/template_manager, none of
    # which this method touches. Build the instance without them and inject only
    # the two collaborators the body actually uses.
    manager = object.__new__(WorkflowAutomationManager)
    manager.orchestrator = orchestrator
    manager.create_automated_workflow = AsyncMock(return_value="workflow-1")

    workflow_id = await manager.create_workflow_from_chat_request("install docker", "session-1")

    # Before #13730 this returned None: enumerate() over a coroutine raised
    # TypeError straight into the handler.
    assert workflow_id == "workflow-1"

    manager.create_automated_workflow.assert_awaited_once()
    steps = manager.create_automated_workflow.await_args.kwargs["steps"]
    assert len(steps) == 3
    assert [step.step_id for step in steps] == ["step_1", "step_2", "step_3"]
    assert all(step.command for step in steps)
    # step_2 is the approval gate, and its dependency on step_1 must have been
    # resolved through task_id — the retired `.id` read is what broke this.
    assert [step.requires_confirmation for step in steps] == [False, True, False]
    assert steps[1].dependencies == ["step_1"]


async def test_generate_smart_steps_awaits_the_plan(orchestrator):
    """SmartStepGenerator iterated a coroutine before #13730."""
    from services.advanced_workflow.step_generator import StepGenerator

    generator = StepGenerator(enhanced_orchestrator=orchestrator)
    generator._generate_alternatives = AsyncMock(return_value=[])
    generator._add_intelligent_bookends = AsyncMock(side_effect=lambda steps, _analysis: steps)

    smart_steps = await generator.generate_smart_steps(
        "install docker",
        {"primary_intent": "configuration", "complexity": "complex"},
        {},
    )

    assert len(smart_steps) == 3
    assert [step.step_id for step in smart_steps] == ["smart_1", "smart_2", "smart_3"]
    assert all(step.command for step in smart_steps)
