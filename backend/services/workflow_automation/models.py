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

from pydantic import BaseModel

from backend.type_defs.common import Metadata


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
