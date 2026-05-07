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
    """Only task_id is required; description defaults to empty string."""
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


def test_workflow_task_task_id_only_construction():
    """Phase 2B (#6951) — legacy enhanced_orchestration.AgentTask had no
    description field. Subclassing the canonical type required dropping the
    `description` requirement so subclass call sites that do not pass
    description still work."""
    t = WorkflowTask(task_id="legacy-style")
    assert t.task_id == "legacy-style"
    assert t.description == ""


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


# ---------------------------------------------------------------------------
# #7124 — to_dict() / from_dict() round-trip tests
# ---------------------------------------------------------------------------


def test_prompt_spec_round_trip():
    """PromptSpec.to_dict() → from_dict() must yield an equal instance."""
    spec = PromptSpec(
        user_prompt="hello {name}",
        system_prompt="you are helpful",
        template_vars={"name": "world"},
        version="3",
    )
    restored = PromptSpec.from_dict(spec.to_dict())
    assert restored == spec


def test_prompt_spec_from_dict_drops_unknown_keys():
    """Forward-compat: unknown keys (added by future server versions) don't
    break older clients deserializing the payload."""
    spec = PromptSpec.from_dict({
        "user_prompt": "hi",
        "version": "1",
        "future_field_we_dont_know_yet": "ignore me",
    })
    assert spec.user_prompt == "hi"
    assert spec.version == "1"


def test_workflow_task_round_trip_minimal():
    """WorkflowTask with only required field round-trips."""
    t = WorkflowTask(task_id="t1")
    restored = WorkflowTask.from_dict(t.to_dict())
    assert restored.task_id == "t1"
    assert restored.description == ""
    assert restored.prompt is None


def test_workflow_task_round_trip_with_prompt():
    """Nested PromptSpec survives round-trip."""
    t = WorkflowTask(
        task_id="t1",
        description="run audit",
        agent_type="security",
        action="run_audit",
        prompt=PromptSpec(user_prompt="audit {target}", version="2"),
        tools_allowed=["read_file", "grep"],
        tools_denied=["shell_exec"],
        estimated_duration_seconds=42.5,
    )
    restored = WorkflowTask.from_dict(t.to_dict())
    assert restored == t
    # Specifically verify the prompt is a PromptSpec, not a dict.
    assert isinstance(restored.prompt, PromptSpec)
    assert restored.prompt.version == "2"


def test_workflow_task_from_dict_requires_task_id():
    """Missing task_id (the only required field) raises KeyError."""
    import pytest
    with pytest.raises(KeyError, match="task_id"):
        WorkflowTask.from_dict({"description": "no task_id"})


def test_workflow_plan_round_trip_with_nested_tasks():
    """Plan with tasks + fallback + strategy enum all survive round-trip."""
    fallback = WorkflowPlan(plan_id="p1-fb", goal="fallback", tasks=[])
    plan = WorkflowPlan(
        plan_id="p1",
        goal="ship feature X",
        tasks=[
            WorkflowTask(task_id="t1", description="design"),
            WorkflowTask(task_id="t2", description="implement", dependencies=["t1"]),
        ],
        strategy=ExecutionStrategy.PIPELINE,
        dependencies_graph={"t2": ["t1"]},
        success_criteria=["all tasks pass"],
        fallback_plans=[fallback],
    )
    restored = WorkflowPlan.from_dict(plan.to_dict())
    assert restored == plan
    # Strategy must be the enum, not the raw string.
    assert restored.strategy is ExecutionStrategy.PIPELINE
    # Nested tasks must be WorkflowTask instances.
    assert isinstance(restored.tasks[0], WorkflowTask)
    # Nested fallback must be a WorkflowPlan.
    assert isinstance(restored.fallback_plans[0], WorkflowPlan)


def test_workflow_plan_to_dict_emits_plain_json():
    """to_dict() output must contain no Enum instances (only string values)
    so the result is plain JSON."""
    plan = WorkflowPlan(
        plan_id="p1",
        goal="g",
        tasks=[],
        strategy=ExecutionStrategy.PARALLEL,
    )
    d = plan.to_dict()
    assert d["strategy"] == "parallel"
    assert not isinstance(d["strategy"], ExecutionStrategy)


def test_workflow_plan_from_dict_accepts_enum_or_string():
    """Tolerate both enum-typed and string-typed strategy in input — useful
    when round-tripping in-memory plans without serialization."""
    base = {"plan_id": "p1", "goal": "g", "tasks": []}
    via_string = WorkflowPlan.from_dict({**base, "strategy": "adaptive"})
    via_enum = WorkflowPlan.from_dict({**base, "strategy": ExecutionStrategy.ADAPTIVE})
    assert via_string.strategy is ExecutionStrategy.ADAPTIVE
    assert via_enum.strategy is ExecutionStrategy.ADAPTIVE


def test_workflow_plan_from_dict_requires_plan_id_goal_tasks():
    """All three required fields validated."""
    import pytest
    for missing in ("plan_id", "goal", "tasks"):
        data = {"plan_id": "p1", "goal": "g", "tasks": []}
        del data[missing]
        with pytest.raises(KeyError, match=missing):
            WorkflowPlan.from_dict(data)
