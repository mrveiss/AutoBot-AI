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

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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
    description: str

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

    metadata: Dict[str, Any] = field(default_factory=dict)


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
