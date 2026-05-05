# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Template Types and Data Classes

Issue #381: Extracted from workflow_templates.py god class refactoring.
Issue #6951: Phase 2A — local WorkflowStep dataclass replaced by an alias to
the canonical autobot_shared.workflow.WorkflowTask. The legacy ``to_dict()``
method is preserved as a free function so the public API contract returned
by ``WorkflowTemplate.to_detail_dict()`` does not change for the frontend
``TemplateStep`` interface (frontend codegen migrates in Phase 2F).

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


def _legacy_step_dict(step: WorkflowTask) -> Dict[str, Any]:
    """Emit the historical TemplateStep dict shape for the public API.

    Phase 2F migrates the frontend ``TemplateStep`` interface to consume the
    canonical ``WorkflowTask`` shape directly; until then this helper preserves
    the wire format. The ``expected_duration_ms`` round-trip is exact because
    the migration script set ``estimated_duration_seconds = ms / 1000.0``.
    """
    return {
        "id": step.task_id,
        "agent_type": step.agent_type or "",
        "action": step.action or "",
        "description": step.description,
        "requires_approval": step.requires_approval,
        "dependencies": step.dependencies,
        "inputs": step.inputs,
        "expected_duration_ms": int(step.estimated_duration_seconds * 1000),
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
            "steps": [_legacy_step_dict(step) for step in self.steps],
        }
