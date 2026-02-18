# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Template Types and Data Classes

Issue #381: Extracted from workflow_templates.py god class refactoring.
Contains core data structures for workflow template definitions.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

from autobot_types import TaskComplexity


class TemplateCategory(Enum):
    """Categories of workflow templates."""

    SECURITY = "security"
    RESEARCH = "research"
    SYSTEM_ADMIN = "system_admin"
    DEVELOPMENT = "development"
    ANALYSIS = "analysis"


@dataclass
class WorkflowStep:
    """Individual step in a workflow template."""

    id: str
    agent_type: str
    action: str
    description: str
    requires_approval: bool = False
    dependencies: List[str] = None
    inputs: Dict[str, Any] = None
    expected_duration_ms: int = 5000

    def __post_init__(self):
        """Initialize default values for dependencies and inputs fields."""
        if self.dependencies is None:
            self.dependencies = []
        if self.inputs is None:
            self.inputs = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to dictionary for caching/serialization."""
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "action": self.action,
            "description": self.description,
            "requires_approval": self.requires_approval,
            "dependencies": self.dependencies,
            "inputs": self.inputs,
            "expected_duration_ms": self.expected_duration_ms,
        }


@dataclass
class WorkflowTemplate:
    """Complete workflow template definition."""

    id: str
    name: str
    description: str
    category: TemplateCategory
    complexity: TaskComplexity
    steps: List[WorkflowStep]
    estimated_duration_minutes: int
    agents_involved: List[str]
    tags: List[str]
    variables: Dict[str, str] = None

    def __post_init__(self):
        """Initialize default value for variables field."""
        if self.variables is None:
            self.variables = {}

    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert template to summary dict for caching."""
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
        }

    def to_detail_dict(self) -> Dict[str, Any]:
        """Convert template to detailed dict for caching."""
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
            "steps": [step.to_dict() for step in self.steps],
        }
