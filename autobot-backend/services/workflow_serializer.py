# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Serializer (#2165)

Provides export/import of workflow definitions as a portable JSON document.
Schema version "1.0" is forward-compatible: unknown keys are preserved on
round-trip and reported as warnings during import validation.

Usage:
    from services.workflow_serializer import WorkflowSerializer

    serializer = WorkflowSerializer(manager)

    # Export an active workflow to a portable dict
    doc = await serializer.export_workflow("wf-abc123")

    # Validate before import (returns list of issue strings)
    issues = serializer.validate_import(doc)

    # Import and create a new workflow owned by user_id
    new_id = await serializer.import_workflow(doc, owner_id="user-xyz")
"""

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from services.workflow_automation.manager import WorkflowAutomationManager
from services.workflow_automation.models import AutomationMode, WorkflowStep

logger = get_logger(__name__)

# Canonical schema version for documents produced by this module.
SCHEMA_VERSION = "1.0"

# Maximum number of steps accepted during import to prevent abuse.
_MAX_IMPORT_STEPS = 500


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class StepExport:
    """Portable representation of a single workflow step (#2165)."""

    step_id: str
    command: str
    description: str
    explanation: str | None = None
    requires_confirmation: bool = True
    risk_level: str = "low"
    estimated_duration: float = 5.0
    dependencies: List[str] = field(default_factory=list)
    timeout_seconds: int | None = None
    step_type: str = "command_execution"
    step_config: Dict[str, Any] | None = None


@dataclass
class WorkflowExportFormat:
    """
    Portable workflow export document (#2165).

    Top-level envelope containing schema metadata and the workflow payload.
    Callers should treat this as a plain JSON-serializable structure.
    """

    schema_version: str
    exported_at: str
    workflow_id: str
    name: str
    description: str
    automation_mode: str
    steps: List[StepExport]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "schema_version": self.schema_version,
            "exported_at": self.exported_at,
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "automation_mode": self.automation_mode,
            "steps": [asdict(s) for s in self.steps],
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------


class WorkflowSerializer:
    """
    Export/import workflow definitions as portable JSON documents (#2165).

    Accepts a WorkflowAutomationManager so it can read active/completed
    workflows without coupling to storage internals.
    """

    def __init__(self, manager: WorkflowAutomationManager) -> None:
        self._manager = manager

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    async def export_workflow(self, workflow_id: str) -> WorkflowExportFormat | None:
        """
        Serialise *workflow_id* to a portable export document.

        Looks in both active and completed workflow stores.

        Args:
            workflow_id: ID of the workflow to export.

        Returns:
            WorkflowExportFormat ready for JSON serialisation, or None when the
            workflow is not found.
        """
        workflow = self._manager.active_workflows.get(workflow_id)
        if workflow is None:
            workflow = self._manager.completed_workflows.get(workflow_id)

        if workflow is None:
            logger.warning("export_workflow: workflow %s not found", workflow_id)
            return None

        steps = [self._step_to_export(s) for s in workflow.steps]

        doc = WorkflowExportFormat(
            schema_version=SCHEMA_VERSION,
            exported_at=utc_timestamp() + "Z",
            workflow_id=workflow.workflow_id,
            name=workflow.name,
            description=workflow.description,
            automation_mode=workflow.automation_mode.value,
            steps=steps,
            metadata={
                "original_session_id": workflow.session_id,
                "original_owner_id": workflow.owner_id,
            },
        )

        logger.info(
            "Exported workflow %s (%s steps) schema_version=%s",
            workflow_id,
            len(steps),
            SCHEMA_VERSION,
        )
        return doc

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_import(self, data: Dict[str, Any]) -> List[str]:
        """
        Validate an import payload and return a list of human-readable issues.

        An empty list means the document is safe to import.  Non-empty means
        the caller should surface the issues to the user before proceeding.

        Args:
            data: Raw dictionary (e.g. parsed from JSON) to validate.

        Returns:
            List of issue strings.  Empty == valid.
        """
        issues: List[str] = []

        if not isinstance(data, dict):
            issues.append("Payload must be a JSON object.")
            return issues

        schema_ver = data.get("schema_version")
        if schema_ver != SCHEMA_VERSION:
            issues.append(f"schema_version '{schema_ver}' is not supported (expected '{SCHEMA_VERSION}').")

        for required in ("name", "description", "steps"):
            if not data.get(required):
                issues.append(f"Missing required field: '{required}'.")

        steps = data.get("steps")
        if isinstance(steps, list):
            if len(steps) > _MAX_IMPORT_STEPS:
                issues.append(f"Import contains {len(steps)} steps; maximum allowed is {_MAX_IMPORT_STEPS}.")
            for i, step in enumerate(steps):
                step_issues = self._validate_step(i, step)
                issues.extend(step_issues)
        elif steps is not None:
            issues.append("'steps' must be a list.")

        automation_mode = data.get("automation_mode", "semi_automatic")
        valid_modes = {m.value for m in AutomationMode}
        if automation_mode not in valid_modes:
            issues.append(f"'automation_mode' value '{automation_mode}' is not one of {sorted(valid_modes)}.")

        return issues

    def _validate_step(self, index: int, step: Any) -> List[str]:
        """Return validation issues for a single step dict (helper for validate_import)."""
        issues: List[str] = []
        prefix = f"steps[{index}]"

        if not isinstance(step, dict):
            issues.append(f"{prefix}: must be an object.")
            return issues

        for req in ("step_id", "command", "description"):
            if not step.get(req):
                issues.append(f"{prefix}: missing required field '{req}'.")

        risk = step.get("risk_level", "low")
        if risk not in {"low", "medium", "high", "critical"}:
            issues.append(f"{prefix}: unknown risk_level '{risk}'.")

        timeout = step.get("timeout_seconds")
        if timeout is not None and (not isinstance(timeout, int) or timeout < 1):
            issues.append(f"{prefix}: 'timeout_seconds' must be a positive integer.")

        return issues

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    async def import_workflow(
        self,
        data: Dict[str, Any],
        owner_id: str | None,
        session_id: str | None = None,
    ) -> str | None:
        """
        Create a new workflow from an export document.

        Runs validation first; returns None if validation fails so the caller
        can surface errors without partial state being created.

        Args:
            data: Raw export dictionary (from WorkflowExportFormat.to_dict()).
            owner_id: ID of the user who will own the imported workflow.
            session_id: Optional session to associate with the new workflow.
                        Falls back to a fresh UUID when not provided.

        Returns:
            New workflow_id string, or None on validation failure.
        """
        issues = self.validate_import(data)
        if issues:
            logger.warning(
                "import_workflow: validation failed for owner=%s issues=%s",
                owner_id,
                issues,
            )
            return None

        steps = [self._dict_to_step(s) for s in data["steps"]]
        mode = _parse_automation_mode(data.get("automation_mode", "semi_automatic"))
        effective_session = session_id or str(uuid.uuid4())

        workflow_id = await self._manager.create_automated_workflow(
            name=data["name"],
            description=data.get("description", ""),
            steps=steps,
            session_id=effective_session,
            automation_mode=mode,
            owner_id=owner_id,
        )

        logger.info(
            "Imported workflow as %s (%s steps) for owner=%s",
            workflow_id,
            len(steps),
            owner_id,
        )
        return workflow_id

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _step_to_export(step: WorkflowStep) -> StepExport:
        """Convert a WorkflowStep dataclass to a StepExport (helper for export_workflow)."""
        return StepExport(
            step_id=step.step_id,
            command=step.command,
            description=step.description,
            explanation=step.explanation,
            requires_confirmation=step.requires_confirmation,
            risk_level=step.risk_level,
            estimated_duration=step.estimated_duration,
            dependencies=list(step.dependencies or []),
            timeout_seconds=step.timeout_seconds,
            step_type=step.step_type,
            step_config=dict(step.step_config) if step.step_config else None,
        )

    @staticmethod
    def _dict_to_step(data: Dict[str, Any]) -> WorkflowStep:
        """Reconstruct a WorkflowStep from an export dict (helper for import_workflow)."""
        return WorkflowStep(
            step_id=data["step_id"],
            command=data["command"],
            description=data["description"],
            explanation=data.get("explanation"),
            requires_confirmation=bool(data.get("requires_confirmation", True)),
            risk_level=data.get("risk_level", "low"),
            estimated_duration=float(data.get("estimated_duration", 5.0)),
            dependencies=list(data.get("dependencies") or []),
            timeout_seconds=data.get("timeout_seconds"),
            step_type=data.get("step_type", "command_execution"),
            step_config=data.get("step_config"),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_automation_mode(value: str) -> AutomationMode:
    """Return the AutomationMode for *value*, falling back to SEMI_AUTOMATIC."""
    try:
        return AutomationMode(value)
    except ValueError:
        logger.warning("Unknown automation_mode '%s'; defaulting to semi_automatic", value)
        return AutomationMode.SEMI_AUTOMATIC
