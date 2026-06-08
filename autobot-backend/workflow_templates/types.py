# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Template Types and Data Classes

Issue #381: Extracted from workflow_templates.py god class refactoring.
Issue #6951: Phase 2A — local WorkflowStep dataclass replaced by an alias to
the canonical autobot_shared.workflow.WorkflowTask.
Issue #6951 Phase 2F + #7044: replaced ``_legacy_step_dict()`` (which emitted
legacy field names ``id`` / ``expected_duration_ms`` to preserve the broken
``TemplateStep`` frontend contract) with ``_template_step_dict()`` that emits
canonical-named fields (``task_id`` / ``estimated_duration_seconds``) plus
the new first-class fields ``command`` / ``prompt`` / ``tools_allowed`` /
``tools_denied``. Frontend ``TemplateStep`` interface and
``WorkflowTemplateGallery.vue`` consumer migrated in lockstep.

Contains core data structures for workflow template definitions.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

from autobot_shared.workflow import WorkflowTask
from autobot_types import TaskComplexity

# Transitional alias — Phase 3 removes this and updates callers to use
# ``WorkflowTask`` directly. Until then, every ``WorkflowStep(task_id=..., ...)``
# call site (#6951 Phase 2A) constructs a real ``WorkflowTask``.
WorkflowStep = WorkflowTask


class TemplateCategory(Enum):
    """Categories of workflow templates."""

    SECURITY = "security"
    RESEARCH = "research"
    SYSTEM_ADMIN = "system_admin"
    DEVELOPMENT = "development"
    ANALYSIS = "analysis"
    COMMUNITY = "community"


def _template_step_dict(step: WorkflowTask) -> Dict[str, Any]:
    """Emit the canonical workflow-template step dict for the public API.

    Replaces the prior ``_legacy_step_dict()`` adapter that #6951 Phase 2A
    introduced as a transitional shim. Field names now match the canonical
    ``WorkflowTask`` shape (``task_id`` / ``estimated_duration_seconds``)
    and the first-class fields added in Phase 1b (``command`` / ``prompt`` /
    ``tools_allowed`` / ``tools_denied``) are emitted so the frontend can
    use them directly.

    Runtime-state fields (``status`` / ``start_time`` / ``end_time`` /
    ``error`` / ``outputs`` / ``retry_count``) are deliberately NOT emitted
    — a *template* step has no execution state. Those belong on the
    ``services/workflow_automation`` runtime path's ``to_status_dict()``,
    which is a separate concern (#7044 split).
    """
    prompt_dict: Dict[str, Any] | None = None
    if step.prompt is not None:
        prompt_dict = {
            "user_prompt": step.prompt.user_prompt,
            "system_prompt": step.prompt.system_prompt,
            "template_vars": step.prompt.template_vars,
            "version": step.prompt.version,
        }
    return {
        "task_id": step.task_id,
        "agent_type": step.agent_type or "",
        "action": step.action or "",
        "command": step.command,
        "description": step.description,
        "requires_approval": step.requires_approval,
        "dependencies": step.dependencies,
        "inputs": step.inputs,
        "estimated_duration_seconds": step.estimated_duration_seconds,
        "prompt": prompt_dict,
        "tools_allowed": step.tools_allowed,
        "tools_denied": step.tools_denied,
    }


@dataclass
class WorkflowTemplate:
    """Complete workflow template definition.

    Note: a ``WorkflowTemplate`` is a static blueprint (category, complexity,
    variable slots, secret requirements). It produces ``WorkflowTask`` lists
    at runtime and is *not* a duplicate of ``WorkflowPlan`` — the plan is the
    runtime execution shape. Phase 2E may relocate this class to
    ``autobot_shared.workflow`` after the advanced_workflow template module
    consolidates onto the same shape.
    """

    id: str
    name: str
    description: str
    category: TemplateCategory
    complexity: TaskComplexity
    steps: List[WorkflowTask]
    estimated_duration_minutes: int
    agents_involved: List[str]
    tags: List[str]
    variables: Dict[str, str] = None
    required_secrets: Dict[str, Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize default values for variables and required_secrets fields."""
        if self.variables is None:
            self.variables = {}
        if self.required_secrets is None:
            self.required_secrets = {}

    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert template to summary dict for caching. (#1415)"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "complexity": self.complexity.value,
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "agents_involved": self.agents_involved,
            "tags": self.tags,
            "step_count": len(self.steps),
            "approval_steps": sum(1 for step in self.steps if step.requires_approval),
            "variables": self.variables,
            "required_secrets": self.required_secrets,
        }

    def to_detail_dict(self) -> Dict[str, Any]:
        """Convert template to detailed dict for caching. (#1415)"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "complexity": self.complexity.value,
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "agents_involved": self.agents_involved,
            "tags": self.tags,
            "variables": self.variables,
            "required_secrets": self.required_secrets,
            "steps": [_template_step_dict(step) for step in self.steps],
        }
