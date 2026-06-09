# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for autobot_shared.workflow.types (#6951)."""

from autobot_shared.workflow import (
    ExecutionStrategy,
    PromptSpec,
    WorkflowPlan,
    WorkflowTask,
)


def test_workflow_task_minimal_construction() -> None:
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


def test_workflow_task_task_id_only_construction() -> None:
    """Phase 2B (#6951) — legacy enhanced_orchestration.AgentTask had no
    description field. Subclassing the canonical type required dropping the
    `description` requirement so subclass call sites that do not pass
    description still work."""
    t = WorkflowTask(task_id="legacy-style")
    assert t.task_id == "legacy-style"
    assert t.description == ""


def test_workflow_task_first_class_prompt() -> None:
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


def test_workflow_task_first_class_tool_gates() -> None:
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


def test_workflow_task_action_and_command_coexist() -> None:
    """``action`` (agent verb) and ``command`` (shell exec) are independent fields."""
    t = WorkflowTask(
        task_id="t1",
        description="d",
        action="run_audit",
        command="bash audit.sh",
    )
    assert t.action == "run_audit"
    assert t.command == "bash audit.sh"


def test_workflow_task_default_factory_isolation() -> None:
    """Mutating one task's mutable defaults must not affect another's."""
    t1 = WorkflowTask(task_id="t1", description="d")
    t2 = WorkflowTask(task_id="t2", description="d")
    t1.dependencies.append("d1")
    t1.tools_denied.append("shell")
    t1.inputs["k"] = "v"
    assert t2.dependencies == []
    assert t2.tools_denied == []
    assert t2.inputs == {}


def test_prompt_spec_minimal_construction() -> None:
    """Only user_prompt is required; other fields default sensibly."""
    spec = PromptSpec(user_prompt="hello")
    assert spec.user_prompt == "hello"
    assert spec.system_prompt is None
    assert spec.template_vars == {}
    assert spec.version == "1"


def test_workflow_plan_minimal_construction() -> None:
    """plan_id, goal, and tasks are required; strategy defaults to SEQUENTIAL."""
    p = WorkflowPlan(plan_id="p1", goal="do work", tasks=[])
    assert p.plan_id == "p1"
    assert p.goal == "do work"
    assert p.tasks == []
    assert p.strategy is ExecutionStrategy.SEQUENTIAL
    assert p.approval_required is True
    assert p.approved is False
    assert p.status == "pending"


def test_workflow_plan_holds_tasks() -> None:
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


def test_execution_strategy_values_match_legacy() -> None:
    """Enum string values stay compatible with the enhanced_orchestration version
    so Phase 2 callers can swap imports without value changes."""
    assert ExecutionStrategy.SEQUENTIAL.value == "sequential"
    assert ExecutionStrategy.PARALLEL.value == "parallel"
    assert ExecutionStrategy.PIPELINE.value == "pipeline"
    assert ExecutionStrategy.COLLABORATIVE.value == "collaborative"
    assert ExecutionStrategy.ADAPTIVE.value == "adaptive"


def test_workflow_plan_supports_nested_fallback_plans() -> None:
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


def test_prompt_spec_round_trip() -> None:
    """PromptSpec.to_dict() → from_dict() must yield an equal instance."""
    spec = PromptSpec(
        user_prompt="hello {name}",
        system_prompt="you are helpful",
        template_vars={"name": "world"},
        version="3",
    )
    restored = PromptSpec.from_dict(spec.to_dict())
    assert restored == spec


def test_prompt_spec_from_dict_drops_unknown_keys() -> None:
    """Forward-compat: unknown keys (added by future server versions) don't
    break older clients deserializing the payload."""
    spec = PromptSpec.from_dict(
        {
            "user_prompt": "hi",
            "version": "1",
            "future_field_we_dont_know_yet": "ignore me",
        }
    )
    assert spec.user_prompt == "hi"
    assert spec.version == "1"


def test_workflow_task_round_trip_minimal() -> None:
    """WorkflowTask with only required field round-trips."""
    t = WorkflowTask(task_id="t1")
    restored = WorkflowTask.from_dict(t.to_dict())
    assert restored.task_id == "t1"
    assert restored.description == ""
    assert restored.prompt is None


def test_workflow_task_round_trip_with_prompt() -> None:
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


def test_workflow_task_from_dict_requires_task_id() -> None:
    """Missing task_id (the only required field) raises KeyError."""
    import pytest

    with pytest.raises(KeyError, match="task_id"):
        WorkflowTask.from_dict({"description": "no task_id"})


def test_workflow_plan_round_trip_with_nested_tasks() -> None:
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


def test_workflow_plan_to_dict_emits_plain_json() -> None:
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


def test_workflow_plan_from_dict_accepts_enum_or_string() -> None:
    """Tolerate both enum-typed and string-typed strategy in input — useful
    when round-tripping in-memory plans without serialization."""
    base = {"plan_id": "p1", "goal": "g", "tasks": []}
    via_string = WorkflowPlan.from_dict({**base, "strategy": "adaptive"})
    via_enum = WorkflowPlan.from_dict({**base, "strategy": ExecutionStrategy.ADAPTIVE})
    assert via_string.strategy is ExecutionStrategy.ADAPTIVE
    assert via_enum.strategy is ExecutionStrategy.ADAPTIVE


def test_workflow_plan_from_dict_requires_plan_id_goal_tasks() -> None:
    """All three required fields validated."""
    import pytest

    for missing in ("plan_id", "goal", "tasks"):
        data = {"plan_id": "p1", "goal": "g", "tasks": []}
        del data[missing]
        with pytest.raises(KeyError, match=missing):
            WorkflowPlan.from_dict(data)


# ---------------------------------------------------------------------------
# #7121 — Lifecycle methods on canonical WorkflowTask
# ---------------------------------------------------------------------------


def test_workflow_task_start_execution_marks_running() -> None:
    """start_execution() sets start_time and status='running'."""
    t = WorkflowTask(task_id="t1")
    assert t.start_time is None
    assert t.status == "pending"
    t.start_execution()
    assert t.start_time is not None
    assert t.status == "running"


def test_workflow_task_complete_execution_records_result() -> None:
    """complete_execution() sets end_time, status='completed', and outputs."""
    t = WorkflowTask(task_id="t1")
    t.start_execution()
    t.complete_execution({"answer": 42})
    assert t.end_time is not None
    assert t.status == "completed"
    assert t.outputs == {"answer": 42}


def test_workflow_task_fail_execution_records_error() -> None:
    """fail_execution() sets status='failed' and error message."""
    t = WorkflowTask(task_id="t1")
    t.fail_execution("network down")
    assert t.status == "failed"
    assert t.error == "network down"


def test_workflow_task_get_execution_time_zero_until_complete() -> None:
    """get_execution_time() returns 0.0 until both start and end are set."""
    t = WorkflowTask(task_id="t1")
    assert t.get_execution_time() == 0.0
    t.start_execution()
    assert t.get_execution_time() == 0.0  # no end yet
    import time as _time

    _time.sleep(0.001)
    t.complete_execution({})
    assert t.get_execution_time() > 0.0


def test_workflow_task_retry_methods() -> None:
    """can_retry() respects max_retries; increment_retry() advances the counter."""
    t = WorkflowTask(task_id="t1", max_retries=2)
    assert t.can_retry()  # 0 < 2
    t.increment_retry()
    assert t.retry_count == 1
    assert t.can_retry()  # 1 < 2
    t.increment_retry()
    assert t.retry_count == 2
    assert not t.can_retry()  # 2 == 2


def test_workflow_task_get_enhanced_inputs_merges_context() -> None:
    """get_enhanced_inputs() returns inputs + context + task_id + workflow_metadata."""
    t = WorkflowTask(
        task_id="t1",
        inputs={"x": 1},
        metadata={"workflow_id": "wf1"},
    )
    enhanced = t.get_enhanced_inputs({"runtime_key": "v"})
    assert enhanced["x"] == 1
    assert enhanced["context"] == {"runtime_key": "v"}
    assert enhanced["task_id"] == "t1"
    assert enhanced["workflow_metadata"] == {"workflow_id": "wf1"}


def test_workflow_task_to_completed_result_shape() -> None:
    """to_completed_result() builds the runner's success-result dict."""
    t = WorkflowTask(task_id="t1", agent_type="researcher")
    t.start_execution()
    import time as _time

    _time.sleep(0.001)
    t.complete_execution({"answer": "yes"})
    res = t.to_completed_result({"answer": "yes"})
    assert res["status"] == "completed"
    assert res["output"] == {"answer": "yes"}
    assert res["execution_time"] > 0.0
    assert res["agent"] == "researcher"


def test_workflow_task_to_failed_result_shape() -> None:
    """to_failed_result() builds the runner's failure-result dict."""
    t = WorkflowTask(task_id="t1", agent_type="researcher")
    res = t.to_failed_result("timeout after 30s")
    assert res["status"] == "failed"
    assert res["error"] == "timeout after 30s"
    assert res["agent"] == "researcher"


def test_lifecycle_methods_inherited_by_subclasses_and_aliases() -> None:
    """#7121 closes the variance gap: all aliases/subclasses now have the methods."""
    # Plain canonical
    plain = WorkflowTask(task_id="plain")
    plain.start_execution()
    assert plain.status == "running"

    # Alias path: workflow_templates.WorkflowStep is `WorkflowStep = WorkflowTask`
    # (#6951 Phase 2A). It must inherit lifecycle methods automatically.
    # Smoke-checked by importer; can't run from autobot_shared without deps.

    # Subclass would also work — covered by enhanced_orchestration tests.


# ---------------------------------------------------------------------------
# #7431 — pending_skill_id field (async Phase 3 gap-fill marker)
# ---------------------------------------------------------------------------


def test_workflow_task_pending_skill_id_defaults_none() -> None:
    """Default leaves pending_skill_id unset — no behavior change for tasks
    that never went through Phase 3 gap-fill."""
    t = WorkflowTask(task_id="t1")
    assert t.pending_skill_id is None


def test_workflow_task_pending_skill_id_explicit_value() -> None:
    """Constructor accepts pending_skill_id directly (planner uses this)."""
    t = WorkflowTask(task_id="t1", pending_skill_id="gen-abc-123")
    assert t.pending_skill_id == "gen-abc-123"


def test_workflow_task_pending_skill_id_round_trip() -> None:
    """to_dict / from_dict preserves the async gap-fill marker so plans
    can be persisted while blocked and resumed after restart."""
    t = WorkflowTask(task_id="t1", pending_skill_id="gen-abc-123")
    restored = WorkflowTask.from_dict(t.to_dict())
    assert restored.pending_skill_id == "gen-abc-123"


def test_workflow_task_pending_skill_id_independent_of_skill_name() -> None:
    """skill_name and pending_skill_id are independent fields. In practice
    they are mutually exclusive (planner sets one OR the other) but the
    dataclass doesn't enforce that — the constraint lives in the planner."""
    t = WorkflowTask(
        task_id="t1",
        skill_name="translation",
        skill_action="translate",
        pending_skill_id=None,
    )
    assert t.skill_name == "translation"
    assert t.pending_skill_id is None
