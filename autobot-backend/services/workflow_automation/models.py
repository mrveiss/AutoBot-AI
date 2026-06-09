# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Automation Models

Enums, dataclasses, and Pydantic models for workflow automation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from services.notification_service import NotificationConfig

from pydantic import BaseModel, Field, field_validator

from type_defs.common import Metadata


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
    risk_assessment: str | None = None
    estimated_total_duration: float = 0.0
    timeout_seconds: int = 300  # 5 minutes default
    created_at: datetime | None = None
    presented_at: datetime | None = None
    resolved_at: datetime | None = None
    user_response: str | None = None

    def __post_init__(self) -> None:
        """Set default created_at timestamp."""
        if self.created_at is None:
            self.created_at = datetime.now(tz=timezone.utc)

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
    explanation: str | None = None
    requires_confirmation: bool = True
    risk_level: str = "low"
    estimated_duration: float = 5.0
    dependencies: List[str] | None = None
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    execution_result: Metadata | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # Issue #2159: Per-step timeout override (seconds). None uses WorkflowLimits default.
    timeout_seconds: int | None = None
    # Issue #2397: Step type — "command_execution" (default) or a vision node type.
    step_type: str = "command_execution"
    # Issue #2397: Step-level configuration dict for vision and future step types.
    step_config: Metadata | None = None

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
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
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
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    user_interventions: List[Metadata] = field(default_factory=list)
    prometheus_start_time: float | None = None  # For Prometheus duration tracking
    # Issue #2153: Owner identifier for workflow secret resolution.
    owner_id: str | None = None
    # Issue #2601: Store step execution results keyed by step_id for reference passing.
    step_results: Dict[str, Metadata] = field(default_factory=dict)
    # Issue #3101: Per-workflow notification routing configuration.
    notification_config: NotificationConfig | None = None
    # Issue #3178: Trigger payload from the event that fired this workflow.
    trigger_payload: Dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Set default values for created_at and user_interventions."""
        if self.created_at is None:
            self.created_at = datetime.now(tz=timezone.utc)
        if self.user_interventions is None:
            self.user_interventions = []

    # === Issue #372: Feature Envy Reduction Methods ===

    # Issue #1380: Current workflow phase from state machine
    phase: str | None = None
    active_service: str | None = None

    def _serialize_notification_config(self) -> Metadata | None:
        """Serialize notification_config to a plain dict for API responses."""
        if self.notification_config is None:
            return None
        from dataclasses import asdict

        return asdict(self.notification_config)

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
            "phase": self.phase,
            "active_service": self.active_service,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
            "steps": [step.to_status_dict() for step in self.steps],
            "user_interventions": self.user_interventions,
            "notification_config": self._serialize_notification_config(),
            "trigger_payload": self.trigger_payload,
        }


# Pydantic models for API requests


class WorkflowStepRequest(BaseModel):
    """Request model for creating a workflow step"""

    command: str
    description: str
    explanation: str | None = None
    requires_confirmation: bool = True
    risk_level: str = "low"
    dependencies: List[str] = []
    # Issue #2159: Per-step timeout in seconds. None means use system default.
    timeout_seconds: int | None = Field(default=None, ge=1)


class AutomatedWorkflowRequest(BaseModel):
    """Request model for creating an automated workflow"""

    name: str
    description: str | None = None
    steps: List[WorkflowStepRequest]
    session_id: str
    automation_mode: str = "semi_automatic"
    timeout_per_step: int = 300  # 5 minutes default


class WorkflowControlRequest(BaseModel):
    """Request model for workflow control actions"""

    workflow_id: str
    action: str  # pause, resume, cancel, approve_step, skip_step
    step_id: str | None = None
    user_input: str | None = None


# Issue #390: Plan Approval API Models
class PlanApprovalResponse(BaseModel):
    """
    User response to plan approval request.

    Issue #390: Handle user's decision on presented plan.
    """

    workflow_id: str
    approved: bool
    approval_mode: str = "full_plan"  # full_plan, per_step, hybrid, auto_safe
    modifications: List[str] | None = None  # Step IDs to modify/skip
    reason: str | None = None  # User's reason for rejection/modification


class PlanPresentationRequest(BaseModel):
    """
    Request to present a workflow plan for approval.

    Issue #390: Trigger plan presentation to user.
    """

    workflow_id: str
    approval_mode: str = "full_plan"
    include_risk_assessment: bool = True
    timeout_seconds: int = 300


# =========================================================================
# Issue #3139: Notification Config API Models
# =========================================================================

_EMAIL_RE = __import__("re").compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_PRIVATE_PREFIXES = (
    "https://10.",
    "https://172.16.",
    "https://172.17.",
    "https://172.18.",
    "https://172.19.",
    "https://172.20.",
    "https://172.21.",
    "https://172.22.",
    "https://172.23.",
    "https://172.24.",
    "https://172.25.",
    "https://172.26.",
    "https://172.27.",
    "https://172.28.",
    "https://172.29.",
    "https://172.30.",
    "https://172.31.",
    "https://192.168.",
    "https://127.",
    "https://169.254.",
    "https://localhost",
)


def _reject_private_url(url: str) -> str:
    """Raise ValueError if URL targets a private/loopback address."""
    for prefix in _PRIVATE_PREFIXES:
        if url.startswith(prefix):
            raise ValueError("Webhook URL must not target private networks")
    return url


class NotificationConfigRequest(BaseModel):
    """
    Request model for updating per-workflow notification routing.

    Issue #3139: Maps notification events to delivery channels.
    """

    enabled: bool = True
    email_recipients: List[str] = Field(default_factory=list)
    slack_webhook_url: str | None = None
    webhook_url: str | None = None
    channels: Dict[str, List[str]] = Field(default_factory=dict)
    templates: Dict[str, str] = Field(default_factory=dict)

    @field_validator("email_recipients", mode="before")
    @classmethod
    def validate_emails(cls, v: List[str]) -> List[str]:
        """Validate email format for each recipient."""
        for email in v:
            if not _EMAIL_RE.match(email):
                raise ValueError("Invalid email: %s" % email)
        return v

    @field_validator("slack_webhook_url", mode="before")
    @classmethod
    def validate_slack_url(cls, v: str | None) -> str | None:
        """Enforce https://hooks.slack.com/ prefix."""
        if not v:
            return v
        if not v.startswith("https://hooks.slack.com/"):
            raise ValueError("Slack webhook must use https://hooks.slack.com/")
        return v

    @field_validator("webhook_url", mode="before")
    @classmethod
    def validate_webhook_url(cls, v: str | None) -> str | None:
        """Enforce https and block private IPs."""
        if not v:
            return v
        if not v.startswith("https://"):
            raise ValueError("Webhook URL must use https://")
        return _reject_private_url(v)
