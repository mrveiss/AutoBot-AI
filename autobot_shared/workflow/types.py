# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Canonical workflow data shapes (#6951).

This module defines the single canonical ``WorkflowTask`` and ``WorkflowPlan``
that replace the eight step shapes and four task shapes that grew out of the
incomplete #381 god-class refactor (closed 2025-12-19, work was extracted
into 3 separate type modules instead of consolidating into one).

Design choices

* **First-class prompt** — ``WorkflowTask.prompt`` is a structured
  ``PromptSpec`` with system/user split + template variables + version, instead
  of being smuggled into the ``action: str`` field as the existing shapes do.
  This enables prompt versioning for cache-key purposes and explicit template
  substitution contracts.
* **First-class tool gates** — ``tools_allowed`` and ``tools_denied`` let a
  step constrain its toolset independently of the agent's capabilities. The
  existing shapes have no per-step tool gate, so a step can only restrict
  tools by switching agents. ``None`` for ``tools_allowed`` means "inherit
  from agent" (current behaviour).
* **Plain string status** — the field type stays ``str`` (matching every
  existing shape) so callers can use ``constants.status_enums.TaskStatus``
  values without ``autobot_shared`` taking a dependency on ``autobot-backend``.
* **Plain string capabilities** — same layering reason; callers can pass
  ``AgentCapability.value`` strings.
* **Both ``action`` and ``command``** — ``action`` is the agent-dispatched
  verb (``summarize_report``, ``run_audit``); ``command`` is the optional
  shell command (``echo 'hello'``). The existing shapes split this concern
  across ``action`` (orchestration/enhanced/templates) and ``command``
  (services/workflow_automation, overseer); the union accommodates both.
"""

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from autobot_shared.status_enums import TaskStatus


class ExecutionStrategy(Enum):
    """Plan-level execution strategy.

    Promoted from ``enhanced_orchestration.types.ExecutionStrategy`` (#381 work
    that should have landed here in the first place).
    """

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"
    COLLABORATIVE = "collaborative"
    ADAPTIVE = "adaptive"


@dataclass
class PromptSpec:
    """Structured prompt for a workflow task.

    Replaces the pattern of smuggling prompt content inside ``action: str`` or
    burying it in ``inputs["prompt"]``. The ``version`` field enables prompt
    cache-key versioning (compatible with #3185 LLMService cache layer).
    """

    user_prompt: str
    system_prompt: Optional[str] = None
    template_vars: Dict[str, Any] = field(default_factory=dict)
    version: str = "1"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dict (#7124)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptSpec":
        """Inverse of ``to_dict()``. Tolerates extra/missing keys for
        forward-compat: unknown keys are dropped, missing keys use defaults."""
        known = {"user_prompt", "system_prompt", "template_vars", "version"}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class WorkflowTask:
    """Canonical task shape — single source of truth for #6951 Phase 2.

    Field union absorbs every field from the four existing task shapes:
    ``orchestration.types.WorkflowStep``, ``enhanced_orchestration.types.AgentTask``,
    ``workflow_templates.types.WorkflowStep``, ``services/workflow_automation.WorkflowStep``,
    and ``agents/overseer/types.AgentTask``. ``orchestration.sub_workflow.SubWorkflowStep``
    is intentionally NOT absorbed — it represents a distinct concern (sub-workflow
    invocation, #2143) and stays separate.
    """

    task_id: str
    description: str = ""

    agent_type: Optional[str] = None
    action: Optional[str] = None
    command: Optional[str] = None

    prompt: Optional[PromptSpec] = None
    tools_allowed: Optional[List[str]] = None
    tools_denied: List[str] = field(default_factory=list)

    inputs: Dict[str, Any] = field(default_factory=dict)
    expected_outputs: Optional[Dict[str, str]] = None
    outputs: Optional[Dict[str, Any]] = None

    dependencies: List[str] = field(default_factory=list)
    requires_approval: bool = False
    priority: int = 5
    timeout_seconds: float = 300.0
    max_retries: int = 3
    retry_count: int = 0

    capabilities_required: List[str] = field(default_factory=list)
    estimated_duration_seconds: float = 0.0

    status: str = "pending"
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    # Skill binding (#7268 Phase 1, ADR-006: Skill-Bound Planning).
    # Populated at plan time by StrategyPlanner via skill_router lookup
    # (dry_run=True — no auto-enable, no Phase 3 gap-fill at plan time).
    # ``skill_name`` is the registered skill name; ``skill_action`` is the
    # action to invoke at execute time; ``skill_resolution_method`` records
    # how it was resolved (``"keyword"`` / ``"llm"`` / ``None``).
    # WorkflowExecutor consumption of these fields is Phase 2 — deferred.
    skill_name: Optional[str] = None
    skill_action: Optional[str] = None
    skill_resolution_method: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Execution lifecycle (#7121, originally #372 → moved to canonical so
    # all subclasses + aliases get the same behavior without duplication.
    # Previously lived on enhanced_orchestration.types.AgentTask only —
    # the variance gap on `WorkflowPlan.tasks: List[WorkflowTask]` allowed
    # plain WorkflowTasks in the list to silently lack these methods.)
    # ------------------------------------------------------------------

    def start_execution(self) -> None:
        """Mark task as started."""
        self.start_time = time.time()
        self.status = TaskStatus.RUNNING.value

    def complete_execution(self, result: Dict[str, Any]) -> None:
        """Mark task as completed with result."""
        self.end_time = time.time()
        self.status = TaskStatus.COMPLETED.value
        self.outputs = result

    def fail_execution(self, error_msg: str) -> None:
        """Mark task as failed with error."""
        self.status = TaskStatus.FAILED.value
        self.error = error_msg

    def get_execution_time(self) -> float:
        """Get execution time in seconds (0.0 when not yet finished)."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        """Increment retry counter."""
        self.retry_count += 1

    def get_enhanced_inputs(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Get inputs enhanced with context (forwarded into agent dispatch)."""
        return {
            **self.inputs,
            "context": context,
            "task_id": self.task_id,
            "workflow_metadata": self.metadata,
        }

    def to_completed_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Build a completed-result dict for the workflow runner."""
        return {
            "status": "completed",
            "output": result,
            "execution_time": self.get_execution_time(),
            "agent": self.agent_type,
        }

    def to_failed_result(self, error_msg: str) -> Dict[str, Any]:
        """Build a failed-result dict for the workflow runner."""
        return {
            "status": "failed",
            "error": error_msg,
            "agent": self.agent_type,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dict (#7124).

        ``prompt`` (a ``PromptSpec``) is recursively serialized via its own
        ``to_dict()`` to keep the wire format consistent with #6951 Phase 2F's
        ``_template_step_dict()`` and to avoid ``asdict()``'s shallow-copy of
        nested dataclasses (which would emit a flat dict losing the
        PromptSpec → JSON contract guarantees).
        """
        d = asdict(self)
        # asdict already recurses into PromptSpec; this re-routes through
        # the canonical PromptSpec.to_dict() so any future format hooks
        # (e.g., omitting None values) live in one place.
        if self.prompt is not None:
            d["prompt"] = self.prompt.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowTask":
        """Inverse of ``to_dict()``. Reconstructs nested ``PromptSpec``.

        Forward-compat: unknown top-level keys are dropped (logged at debug
        if a logger is configured by the caller), missing keys use defaults.
        Required field ``task_id`` raises ``KeyError`` if absent.
        """
        if "task_id" not in data:
            raise KeyError("WorkflowTask.from_dict requires 'task_id'")
        prompt_data = data.get("prompt")
        prompt = PromptSpec.from_dict(prompt_data) if isinstance(prompt_data, dict) else None
        known = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs = {k: v for k, v in data.items() if k in known and k != "prompt"}
        kwargs["prompt"] = prompt
        return cls(**kwargs)


@dataclass
class WorkflowPlan:
    """Canonical plan shape — single source of truth for #6951 Phase 2.

    Field union absorbs every field from the two existing plan shapes:
    ``orchestration.types.WorkflowPlan`` (workflow_id, approval_required, approved)
    and ``enhanced_orchestration.types.WorkflowPlan`` (plan_id, goal, strategy,
    dependencies_graph, success_criteria, fallback_plans).
    """

    plan_id: str
    goal: str
    tasks: List[WorkflowTask]

    description: str = ""
    strategy: ExecutionStrategy = ExecutionStrategy.SEQUENTIAL
    dependencies_graph: Dict[str, List[str]] = field(default_factory=dict)
    estimated_total_duration_seconds: float = 0.0
    resource_requirements: Dict[str, Any] = field(default_factory=dict)
    success_criteria: List[str] = field(default_factory=list)
    fallback_plans: List["WorkflowPlan"] = field(default_factory=list)

    approval_required: bool = True
    approved: bool = False
    status: str = "pending"

    created_at_epoch: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dict (#7124).

        Recursively serializes nested ``WorkflowTask`` and ``WorkflowPlan``
        (fallback) instances via their own ``to_dict()`` methods. The
        ``ExecutionStrategy`` enum is downgraded to its string value so the
        result is plain JSON (no enum instances remain).
        """
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "tasks": [t.to_dict() for t in self.tasks],
            "description": self.description,
            "strategy": self.strategy.value,
            "dependencies_graph": self.dependencies_graph,
            "estimated_total_duration_seconds": self.estimated_total_duration_seconds,
            "resource_requirements": self.resource_requirements,
            "success_criteria": self.success_criteria,
            "fallback_plans": [p.to_dict() for p in self.fallback_plans],
            "approval_required": self.approval_required,
            "approved": self.approved,
            "status": self.status,
            "created_at_epoch": self.created_at_epoch,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowPlan":
        """Inverse of ``to_dict()``. Reconstructs nested tasks + fallback plans
        + ``ExecutionStrategy`` enum.

        Required fields ``plan_id``, ``goal``, ``tasks`` raise ``KeyError`` if
        absent. Unknown keys are dropped for forward-compat.
        """
        for required in ("plan_id", "goal", "tasks"):
            if required not in data:
                raise KeyError(f"WorkflowPlan.from_dict requires '{required}'")
        tasks = [WorkflowTask.from_dict(t) for t in data["tasks"]]
        fallback_plans_raw = data.get("fallback_plans", [])
        fallback_plans = [cls.from_dict(p) for p in fallback_plans_raw]
        strategy_raw = data.get("strategy", ExecutionStrategy.SEQUENTIAL.value)
        strategy = strategy_raw if isinstance(strategy_raw, ExecutionStrategy) else ExecutionStrategy(strategy_raw)
        known = {f.name for f in cls.__dataclass_fields__.values()}
        nested_keys = {"tasks", "fallback_plans", "strategy"}
        kwargs = {k: v for k, v in data.items() if k in known and k not in nested_keys}
        kwargs["tasks"] = tasks
        kwargs["fallback_plans"] = fallback_plans
        kwargs["strategy"] = strategy
        return cls(**kwargs)
