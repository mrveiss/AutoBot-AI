# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request and response schemas for ``api/approval_gates.py`` (#6042, #13421).

Split out of ``schemas_workflows.py``, which is over the file-size ceiling and may not grow.
"""

from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from autobot_shared.risk_tier import RiskTier
from models.approval import ApprovalSource, ApprovalType


class AuthorTypeEnum(str, Enum):
    """Valid author types for approval comments."""

    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class CreateApprovalRequest(BaseModel):
    """Request body for creating an approval gate."""

    title: str
    approval_type: ApprovalType
    description: str | None = None
    requested_by_agent: str | None = None
    workflow_id: str | None = None
    workflow_step: str | None = None
    context: Dict[str, Any] | None = None
    task_ids: List[str] | None = None


class ApprovalTransitionRequest(BaseModel):
    """Request body for approve / reject / request-revision."""

    comment: str | None = None


class ApprovalResubmitRequest(BaseModel):
    """Request body for resubmitting after revision."""

    description: str | None = None
    context: Dict[str, Any] | None = None


class ApprovalAddCommentRequest(BaseModel):
    """Comment on an approval gate. author_type is ignored (#17056) -- kept only to log an old client sending it."""

    body: str
    author_type: AuthorTypeEnum | None = None


class ApprovalLinkTaskRequest(BaseModel):
    """Request body for linking a task to an approval gate."""

    task_id: str
    task_type: str = "github_issue"


class TaskApprovalLinkResponse(BaseModel):
    """A task or issue linked to an approval, nested in ``ApprovalGateResponse``."""

    id: str
    approval_id: str
    task_id: str
    task_type: str


class ApprovalCommentResponse(BaseModel):
    """Response for an approval gate comment."""

    id: str
    approval_id: str
    author: str
    author_type: str
    body: str
    created_at: str | None = None


class ApprovalGateResponse(BaseModel):
    """One approval record as the API returns it, including the #13421 source, risk tier and expiry."""

    id: str
    title: str
    description: str | None = None
    approval_type: str
    status: str
    requested_by_agent: str | None = None
    decided_by_user: str | None = None
    workflow_id: str | None = None
    workflow_step: str | None = None
    context: Dict[str, Any] | None = None
    decided_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # One-approval-record fields (#13421); None for approvals that predate them.
    source: ApprovalSource | None = None
    risk_tier: RiskTier | None = None
    expires_at: str | None = None
    payload_hash: str | None = None
    resume_ref: str | None = None
    comments: List[ApprovalCommentResponse] = Field(default_factory=list)
    task_links: List[TaskApprovalLinkResponse] = Field(default_factory=list)
