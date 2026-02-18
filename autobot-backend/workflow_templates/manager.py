# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Template Manager

Issue #381: Extracted from workflow_templates.py god class refactoring.
Lean coordinator that manages workflow templates using composition pattern.
"""

from typing import Any, Dict, List, Optional

from autobot_types import TaskComplexity

from .analysis import get_all_analysis_templates
from .development import get_all_development_templates
from .research import get_all_research_templates
from .security import get_all_security_templates
from .sysadmin import get_all_sysadmin_templates
from .types import TemplateCategory, WorkflowTemplate


class WorkflowTemplateManager:
    """Manages workflow templates and provides template-based execution."""

    def __init__(self):
        """Initialize template manager and load default templates."""
        self.templates: Dict[str, WorkflowTemplate] = {}
        self._initialize_default_templates()

    def _initialize_default_templates(self):
        """Initialize default workflow templates from all categories."""
        # Load templates from category-specific modules
        all_templates = (
            get_all_security_templates()
            + get_all_research_templates()
            + get_all_sysadmin_templates()
            + get_all_development_templates()
            + get_all_analysis_templates()
        )

        for template in all_templates:
            self.templates[template.id] = template

    def get_template(self, template_id: str) -> Optional[WorkflowTemplate]:
        """Get a workflow template by ID."""
        return self.templates.get(template_id)

    def list_templates(
        self,
        category: Optional[TemplateCategory] = None,
        tags: Optional[List[str]] = None,
    ) -> List[WorkflowTemplate]:
        """List workflow templates, optionally filtered by category or tags."""
        templates = list(self.templates.values())

        if category:
            templates = [t for t in templates if t.category == category]

        if tags:
            templates = [t for t in templates if any(tag in t.tags for tag in tags)]

        return sorted(templates, key=lambda t: t.name)

    def get_templates_by_complexity(
        self, complexity: TaskComplexity
    ) -> List[WorkflowTemplate]:
        """Get templates by complexity level."""
        return [
            template
            for template in self.templates.values()
            if template.complexity == complexity
        ]

    def search_templates(self, query: str) -> List[WorkflowTemplate]:
        """Search templates by name, description, or tags."""
        query_lower = query.lower()
        matching_templates = []

        for template in self.templates.values():
            if (
                query_lower in template.name.lower()
                or query_lower in template.description.lower()
                or any(query_lower in tag.lower() for tag in template.tags)
            ):
                matching_templates.append(template)

        return sorted(matching_templates, key=lambda t: t.name)

    def create_workflow_from_template(
        self, template_id: str, variables: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a workflow instance from a template with variable substitution."""
        template = self.get_template(template_id)
        if not template:
            return None

        # Apply variable substitution if provided
        variables = variables or {}

        # Create workflow steps from template
        workflow_steps = []
        for step in template.steps:
            workflow_step = {
                "step_id": step.id,
                "agent_type": step.agent_type,
                "action": self._substitute_variables(step.action, variables),
                "description": self._substitute_variables(step.description, variables),
                "requires_approval": step.requires_approval,
                "dependencies": step.dependencies.copy(),
                "inputs": step.inputs.copy() if step.inputs else {},
                "expected_duration_ms": step.expected_duration_ms,
                "status": "pending",
            }
            workflow_steps.append(workflow_step)

        return {
            "template_id": template_id,
            "template_name": template.name,
            "description": self._substitute_variables(template.description, variables),
            "category": template.category.value,
            "complexity": template.complexity.value,
            "estimated_duration_minutes": template.estimated_duration_minutes,
            "agents_involved": template.agents_involved.copy(),
            "tags": template.tags.copy(),
            "steps": workflow_steps,
            "variables_used": variables,
        }

    def _substitute_variables(self, text: str, variables: Dict[str, str]) -> str:
        """Substitute template variables in text."""
        for var_name, var_value in variables.items():
            placeholder = f"{{{var_name}}}"
            text = text.replace(placeholder, var_value)
        return text

    def get_template_variables(self, template_id: str) -> Dict[str, str]:
        """Get the variables defined for a template."""
        template = self.get_template(template_id)
        return template.variables if template else {}

    def validate_template_variables(
        self, template_id: str, variables: Dict[str, str]
    ) -> Dict[str, Any]:
        """Validate provided variables against template requirements."""
        template = self.get_template(template_id)
        if not template:
            return {"valid": False, "error": "Template not found"}

        required_vars = set(template.variables.keys())
        provided_vars = set(variables.keys())

        missing_vars = required_vars - provided_vars
        extra_vars = provided_vars - required_vars

        return {
            "valid": len(missing_vars) == 0,
            "missing_variables": list(missing_vars),
            "extra_variables": list(extra_vars),
            "template_variables": template.variables,
        }
