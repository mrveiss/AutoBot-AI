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

from unittest.mock import AsyncMock, MagicMock

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


async def test_create_workflow_from_chat_request_uses_llm_planner():
    """#13809: chat-driven workflow creation uses canonical LLM planner.

    plan_workflow_steps returned a fixed skeleton that _extract_command_from_step
    could never match, so every chat request produced identical echo steps.
    create_workflow_plan is the canonical planner (#13751) and produces real plans.
    """
    from autobot_shared.workflow.types import WorkflowPlan, WorkflowTask
    from services.workflow_automation.manager import WorkflowAutomationManager

    plan = WorkflowPlan(
        plan_id="plan-1",
        goal="install docker",
        tasks=[
            WorkflowTask(
                task_id="step_1",
                action="analyze_request",
                command="echo 'analyzing'",
                requires_approval=False,
                dependencies=[],
            ),
            WorkflowTask(
                task_id="step_2",
                action="execute_plan",
                command="sudo apt install -y docker",
                requires_approval=True,
                dependencies=["step_1"],
            ),
            WorkflowTask(
                task_id="step_3",
                action="synthesize_results",
                command="echo 'done'",
                requires_approval=False,
                dependencies=["step_2"],
            ),
        ],
    )

    manager = object.__new__(WorkflowAutomationManager)
    manager.orchestrator = MagicMock()
    manager.orchestrator.create_workflow_plan = AsyncMock(return_value=plan)
    manager.create_automated_workflow = AsyncMock(return_value="workflow-1")

    workflow_id = await manager.create_workflow_from_chat_request("install docker", "session-1")

    assert workflow_id == "workflow-1"

    manager.create_automated_workflow.assert_awaited_once()
    steps = manager.create_automated_workflow.await_args.kwargs["steps"]
    assert len(steps) == 3
    assert [step.step_id for step in steps] == ["step_1", "step_2", "step_3"]
    assert [step.command for step in steps] == [
        "echo 'analyzing'",
        "sudo apt install -y docker",
        "echo 'done'",
    ]
    assert [step.requires_confirmation for step in steps] == [False, True, False]
    assert steps[1].dependencies == ["step_1"]
    assert steps[2].dependencies == ["step_2"]


async def test_two_chat_requests_yield_different_workflow_steps():
    """#13809 acceptance: different requests produce different workflow steps.

    The old plan_workflow_steps skeleton returned three identical echo steps
    for every request regardless of content. The LLM planner must produce
    distinct plans for distinct inputs.
    """
    from autobot_shared.workflow.types import WorkflowPlan, WorkflowTask
    from services.workflow_automation.manager import WorkflowAutomationManager

    plan_install = WorkflowPlan(
        plan_id="plan-install",
        goal="install docker",
        tasks=[
            WorkflowTask(
                task_id="step_1",
                action="install_docker",
                command="sudo apt install -y docker",
                requires_approval=False,
            ),
        ],
    )
    plan_wipe = WorkflowPlan(
        plan_id="plan-wipe",
        goal="wipe logs",
        tasks=[
            WorkflowTask(
                task_id="step_1",
                action="locate_logs",
                command="find /var/log -name '*.log'",
                requires_approval=False,
            ),
            WorkflowTask(
                task_id="step_2",
                action="wipe_logs",
                command="sudo rm -f /var/log/*.log",
                requires_approval=True,
                dependencies=["step_1"],
            ),
        ],
    )

    manager = object.__new__(WorkflowAutomationManager)
    manager.orchestrator = MagicMock()
    manager.orchestrator.create_workflow_plan = AsyncMock(side_effect=[plan_install, plan_wipe])
    manager.create_automated_workflow = AsyncMock(side_effect=["wf-install", "wf-wipe"])

    wf_install = await manager.create_workflow_from_chat_request("install docker", "s1")
    wf_wipe = await manager.create_workflow_from_chat_request("wipe logs", "s2")

    assert wf_install == "wf-install"
    assert wf_wipe == "wf-wipe"

    assert manager.create_automated_workflow.call_count == 2
    steps_install = manager.create_automated_workflow.await_args_list[0].kwargs["steps"]
    steps_wipe = manager.create_automated_workflow.await_args_list[1].kwargs["steps"]

    assert len(steps_install) != len(steps_wipe)
    assert steps_install[0].command != steps_wipe[0].command


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
