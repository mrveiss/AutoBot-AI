# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for autobot_shared.workflow.types (#6951)."""

from autobot_shared.workflow import (
    ExecutionStrategy,
    PromptSpec,
    WorkflowPlan,
    WorkflowTask,
)


def test_workflow_task_minimal_construction():
    """Only task_id and description are required."""
    t = WorkflowTask(task_id="t1", description="do the thing")
    assert t.task_id == "t1"
    assert t.description == "do the thing"
    assert t.status == "pending"
    assert t.prompt is None
    assert t.tools_allowed is None
    assert t.tools_denied == []
    assert t.inputs == {}
    assert t.dependencies == []
    assert t.metadata == {}


def test_workflow_task_first_class_prompt():
    """PromptSpec attaches to the task and preserves all fields."""
    spec = PromptSpec(
        user_prompt="summarize {report}",
        system_prompt="you are a helpful summarizer",
        template_vars={"report": "Q3 sales"},
        version="2",
    )
    t = WorkflowTask(task_id="t1", description="summarize", prompt=spec)
    assert t.prompt is spec
    assert t.prompt.user_prompt == "summarize {report}"
    assert t.prompt.system_prompt == "you are a helpful summarizer"
    assert t.prompt.template_vars == {"report": "Q3 sales"}
    assert t.prompt.version == "2"


def test_workflow_task_first_class_tool_gates():
    """tools_allowed=None means inherit; explicit list locks the toolset."""
    inherit = WorkflowTask(task_id="t1", description="d")
    assert inherit.tools_allowed is None

    locked = WorkflowTask(
        task_id="t2",
        description="d",
        tools_allowed=["read_file", "grep"],
        tools_denied=["shell_exec"],
    )
    assert locked.tools_allowed == ["read_file", "grep"]
    assert locked.tools_denied == ["shell_exec"]


def test_workflow_task_action_and_command_coexist():
    """``action`` (agent verb) and ``command`` (shell exec) are independent fields."""
    t = WorkflowTask(
        task_id="t1",
        description="d",
        action="run_audit",
        command="bash audit.sh",
    )
    assert t.action == "run_audit"
    assert t.command == "bash audit.sh"


def test_workflow_task_default_factory_isolation():
    """Mutating one task's mutable defaults must not affect another's."""
    t1 = WorkflowTask(task_id="t1", description="d")
    t2 = WorkflowTask(task_id="t2", description="d")
    t1.dependencies.append("d1")
    t1.tools_denied.append("shell")
    t1.inputs["k"] = "v"
    assert t2.dependencies == []
    assert t2.tools_denied == []
    assert t2.inputs == {}


def test_prompt_spec_minimal_construction():
    """Only user_prompt is required; other fields default sensibly."""
    spec = PromptSpec(user_prompt="hello")
    assert spec.user_prompt == "hello"
    assert spec.system_prompt is None
    assert spec.template_vars == {}
    assert spec.version == "1"


def test_workflow_plan_minimal_construction():
    """plan_id, goal, and tasks are required; strategy defaults to SEQUENTIAL."""
    p = WorkflowPlan(plan_id="p1", goal="do work", tasks=[])
    assert p.plan_id == "p1"
    assert p.goal == "do work"
    assert p.tasks == []
    assert p.strategy is ExecutionStrategy.SEQUENTIAL
    assert p.approval_required is True
    assert p.approved is False
    assert p.status == "pending"


def test_workflow_plan_holds_tasks():
    """Plan composes WorkflowTasks and dependency graph stays separate."""
    t1 = WorkflowTask(task_id="t1", description="first")
    t2 = WorkflowTask(task_id="t2", description="second", dependencies=["t1"])
    p = WorkflowPlan(
        plan_id="p1",
        goal="g",
        tasks=[t1, t2],
        dependencies_graph={"t2": ["t1"]},
        strategy=ExecutionStrategy.PIPELINE,
    )
    assert len(p.tasks) == 2
    assert p.tasks[1].dependencies == ["t1"]
    assert p.dependencies_graph == {"t2": ["t1"]}
    assert p.strategy is ExecutionStrategy.PIPELINE


def test_execution_strategy_values_match_legacy():
    """Enum string values stay compatible with the enhanced_orchestration version
    so Phase 2 callers can swap imports without value changes."""
    assert ExecutionStrategy.SEQUENTIAL.value == "sequential"
    assert ExecutionStrategy.PARALLEL.value == "parallel"
    assert ExecutionStrategy.PIPELINE.value == "pipeline"
    assert ExecutionStrategy.COLLABORATIVE.value == "collaborative"
    assert ExecutionStrategy.ADAPTIVE.value == "adaptive"


def test_workflow_plan_supports_nested_fallback_plans():
    """fallback_plans takes other WorkflowPlan instances (forward ref)."""
    fallback = WorkflowPlan(plan_id="p1-fb", goal="fallback", tasks=[])
    primary = WorkflowPlan(
        plan_id="p1",
        goal="g",
        tasks=[],
        fallback_plans=[fallback],
    )
    assert primary.fallback_plans[0].plan_id == "p1-fb"
