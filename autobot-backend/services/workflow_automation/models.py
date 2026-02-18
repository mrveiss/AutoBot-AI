# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Automation Models

Enums, dataclasses, and Pydantic models for workflow automation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from backend.type_defs.common import Metadata
from pydantic import BaseModel


class WorkflowStepStatus(Enum):
    """Status of a workflow step"""

    PENDING = "pending"
    WAITING_APPROVAL = "waiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    PAUSED = "paused"


class AutomationMode(Enum):
    """Automation execution modes"""

    MANUAL = "manual"
    SEMI_AUTOMATIC = "semi_automatic"  # Requires user confirmation
    AUTOMATIC = "automatic"  # Auto-execute safe commands


# Issue #390: Plan Approval System Models
class PlanApprovalMode(Enum):
    """
    Plan approval modes for multi-step task execution.

    Issue #390: Multi-step tasks should present plan before execution.
    """

    FULL_PLAN_APPROVAL = "full_plan"  # Approve entire plan at once
    PER_STEP_APPROVAL = "per_step"  # Approve each step individually
    HYBRID_APPROVAL = "hybrid"  # Approve plan + critical steps separately
    AUTO_SAFE_STEPS = "auto_safe"  # Auto-approve low-risk, ask for high-risk


class PlanApprovalStatus(Enum):
    """
    Status of plan approval request.

    Issue #390: Track plan approval state.
    """

    PENDING = "pending"  # Plan created, awaiting presentation
    PRESENTED = "presented"  # Plan shown to user
    AWAITING_APPROVAL = "awaiting_approval"  # Waiting for user decision
    APPROVED = "approved"  # User approved the plan
    REJECTED = "rejected"  # User rejected the plan
    MODIFIED = "modified"  # User requested modifications
    TIMEOUT = "timeout"  # Approval request timed out


@dataclass
class PlanApprovalRequest:
    """
    Request for plan approval before workflow execution.

    Issue #390: Present plan to user and wait for approval.
    """

    workflow_id: str
    plan_summary: str
    total_steps: int
    steps_preview: List["WorkflowStep"]
    approval_mode: PlanApprovalMode = PlanApprovalMode.FULL_PLAN_APPROVAL
    status: PlanApprovalStatus = PlanApprovalStatus.PENDING
    risk_assessment: Optional[str] = None
    estimated_total_duration: float = 0.0
    timeout_seconds: int = 300  # 5 minutes default
    created_at: Optional[datetime] = None
    presented_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    user_response: Optional[str] = None

    def __post_init__(self):
        """Set default created_at timestamp."""
        if self.created_at is None:
            self.created_at = datetime.now()

    def to_presentation_dict(self) -> Metadata:
        """Convert to dictionary for frontend presentation."""
        return {
            "workflow_id": self.workflow_id,
            "plan_summary": self.plan_summary,
            "total_steps": self.total_steps,
            "steps": [
                {
                    "step_id": step.step_id,
                    "command": step.command,
                    "description": step.description,
                    "risk_level": step.risk_level,
                    "requires_confirmation": step.requires_confirmation,
                    "estimated_duration": step.estimated_duration,
                }
                for step in self.steps_preview
            ],
            "approval_mode": self.approval_mode.value,
            "status": self.status.value,
            "risk_assessment": self.risk_assessment,
            "estimated_total_duration": self.estimated_total_duration,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class WorkflowStep:
    """Individual step in an automated workflow"""

    step_id: str
    command: str
    description: str
    explanation: Optional[str] = None
    requires_confirmation: bool = True
    risk_level: str = "low"
    estimated_duration: float = 5.0
    dependencies: Optional[List[str]] = None
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    execution_result: Optional[Metadata] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # === Issue #372: Feature Envy Reduction Methods ===

    def to_status_dict(self) -> Metadata:
        """Convert step to status dictionary (Issue #372 - reduces feature envy)."""
        return {
            "step_id": self.step_id,
            "command": self.command,
            "description": self.description,
            "status": self.status.value,
            "requires_confirmation": self.requires_confirmation,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
        }


@dataclass
class ActiveWorkflow:
    """Active workflow session state"""

    workflow_id: str
    name: str
    description: str
    session_id: str
    steps: List[WorkflowStep]
    current_step_index: int = 0
    automation_mode: AutomationMode = AutomationMode.SEMI_AUTOMATIC
    is_paused: bool = False
    is_cancelled: bool = False
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    user_interventions: List[Metadata] = field(default_factory=list)
    prometheus_start_time: Optional[float] = None  # For Prometheus duration tracking

    def __post_init__(self):
        """Set default values for created_at and user_interventions."""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.user_interventions is None:
            self.user_interventions = []

    # === Issue #372: Feature Envy Reduction Methods ===

    def to_status_dict(self) -> Metadata:
        """Convert workflow to status dictionary (Issue #372 - reduces feature envy)."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "session_id": self.session_id,
            "current_step": self.current_step_index + 1,
            "total_steps": len(self.steps),
            "is_paused": self.is_paused,
            "is_cancelled": self.is_cancelled,
            "automation_mode": self.automation_mode.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "steps": [step.to_status_dict() for step in self.steps],
            "user_interventions": self.user_interventions,
        }


# Pydantic models for API requests


class WorkflowStepRequest(BaseModel):
    """Request model for creating a workflow step"""

    command: str
    description: str
    explanation: Optional[str] = None
    requires_confirmation: bool = True
    risk_level: str = "low"
    dependencies: List[str] = []


class AutomatedWorkflowRequest(BaseModel):
    """Request model for creating an automated workflow"""

    name: str
    description: Optional[str] = None
    steps: List[WorkflowStepRequest]
    session_id: str
    automation_mode: str = "semi_automatic"
    timeout_per_step: int = 300  # 5 minutes default


class WorkflowControlRequest(BaseModel):
    """Request model for workflow control actions"""

    workflow_id: str
    action: str  # pause, resume, cancel, approve_step, skip_step
    step_id: Optional[str] = None
    user_input: Optional[str] = None


# Issue #390: Plan Approval API Models
class PlanApprovalResponse(BaseModel):
    """
    User response to plan approval request.

    Issue #390: Handle user's decision on presented plan.
    """

    workflow_id: str
    approved: bool
    approval_mode: str = "full_plan"  # full_plan, per_step, hybrid, auto_safe
    modifications: Optional[List[str]] = None  # Step IDs to modify/skip
    reason: Optional[str] = None  # User's reason for rejection/modification


class PlanPresentationRequest(BaseModel):
    """
    Request to present a workflow plan for approval.

    Issue #390: Trigger plan presentation to user.
    """

    workflow_id: str
    approval_mode: str = "full_plan"
    include_risk_assessment: bool = True
    timeout_seconds: int = 300
