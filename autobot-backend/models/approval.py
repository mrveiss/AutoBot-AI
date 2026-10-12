# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Approval Gate Models (#1402)

SQLAlchemy models for human-in-the-loop approval gates.
"""

import uuid
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class ApprovalStatus(str, Enum):
    """Possible statuses for an approval gate.

    Canonical for both the platform-general and the LLC company-scoped case
    (#17043): WITHDRAWN/EXPIRED were LLC-only until this merge.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class ApprovalType(str, Enum):
    """Categories of approval gates.

    Canonical for both the platform-general and the LLC company-scoped case
    (#17043): HIRE..FINDING_PROMOTION were LLC-only (``llc/models/enums.py``)
    until this merge -- ``llc.models.enums.ApprovalType`` now re-exports this
    class rather than defining its own, so the two never drift apart again.
    """

    DESTRUCTIVE_ACTION = "destructive_action"
    RESOURCE_REQUEST = "resource_request"
    CREATE_AGENT = "create_agent"
    WORKFLOW_GATE = "workflow_gate"
    HIRE = "hire"
    STRATEGY = "strategy"
    BUDGET_OVERRIDE = "budget_override"
    SPRINT_CLOSE = "sprint_close"
    PROJECT_DISPOSAL = "project_disposal"
    FINDING_PROMOTION = "finding_promotion"


class ApprovalSource(str, Enum):
    """Which surface raised an approval (#13421).

    The seven pre-existing approval surfaces plus the MCP tool-schema gate (#13414).
    ``terminal_command`` covers both the chat command card and the command permission
    dialog -- they share one backend. Stored in ``Approval.source`` (nullable: rows
    created before #13421, and the LLC company case, carry none).
    """

    TERMINAL_COMMAND = "terminal_command"
    AGENT_TOOL = "agent_tool"
    WORKFLOW_PLAN = "workflow_plan"
    PLUGIN_CAPABILITY = "plugin_capability"
    AUTORESEARCH = "autoresearch"
    SKILL_GOVERNANCE = "skill_governance"
    COMPANY = "company"
    MCP_TOOL_SCHEMA = "mcp_tool_schema"


class Approval(Base):
    """A human-in-the-loop approval gate request (#1402)."""

    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_company_status", "company_id", "status"),)

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    approval_type = Column(
        String(50),
        nullable=False,
        index=True,
    )
    status = Column(
        String(30),
        nullable=False,
        default=ApprovalStatus.PENDING.value,
        index=True,
    )
    # NULL = platform-general (unscoped); set = an LLC company-scoped approval
    # (#17043). No FK: matches the pre-merge llc_approvals.company_id, which
    # was never FK-constrained either.
    company_id = Column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )
    # A caller-supplied identifier: a plain string for a platform-general
    # requester, or an LLC agent's UUID stringified (#17043 merge -- LLC's
    # requested_by_agent_id column becomes this column's value, not a second
    # typed column, since this one already had no type constraint to violate).
    requested_by_agent = Column(
        String(255),
        nullable=True,
        index=True,
    )
    decided_by_user = Column(String(255), nullable=True)
    workflow_id = Column(
        String(255),
        nullable=True,
        index=True,
    )
    workflow_step = Column(String(255), nullable=True)
    context = Column(JSONB, nullable=True, default=dict)
    # timezone=True (#17072 CI): the unified table now also receives
    # llc_approvals' tz-aware decided_at values (migration 20260918_094).
    decided_at = Column(DateTime(timezone=True), nullable=True)
    # One-approval-record columns (#13421 S1). All nullable: rows that predate the
    # migration (and the LLC case) keep NULL and are never rewritten.
    source = Column(String(50), nullable=True, index=True)  # ApprovalSource value
    risk_tier = Column(String(20), nullable=True, index=True)  # autobot_shared.risk_tier.RiskTier value
    expires_at = Column(DateTime(timezone=True), nullable=True)
    payload_hash = Column(String(64), nullable=True)  # sha256 hex of the proposed payload
    resume_ref = Column(String(255), nullable=True)  # key the source's resume handler continues from
    # Username (session ``metadata.owner``, never a user id) of the person whose session raised a
    # sourced approval; the pending list shows it to that user only (#18413, THREAT_MODEL s2).
    owner_user = Column(String(255), nullable=True, index=True)

    # Relationships
    comments = relationship(
        "ApprovalComment",
        back_populates="approval",
        cascade="all, delete-orphan",
        order_by="ApprovalComment.created_at",
    )
    task_links = relationship(
        "TaskApprovalLink",
        back_populates="approval",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Approval id={self.id} " f"type={self.approval_type} " f"status={self.status}>"


class ApprovalComment(Base):
    """A comment on an approval gate (#1402)."""

    __tablename__ = "approval_comments"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    approval_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("approvals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author = Column(String(255), nullable=False)
    author_type = Column(
        String(20),
        nullable=False,
        default="human",
    )
    body = Column(Text, nullable=False)

    # Relationships
    approval = relationship(
        "Approval",
        back_populates="comments",
    )

    def __repr__(self) -> str:
        return f"<ApprovalComment id={self.id} " f"author={self.author}>"


class TaskApprovalLink(Base):
    """Links a task/issue to an approval gate (#1402)."""

    __tablename__ = "task_approval_links"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    approval_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("approvals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id = Column(
        String(255),
        nullable=False,
        index=True,
    )
    task_type = Column(
        String(50),
        nullable=False,
        default="github_issue",
    )

    # Relationships
    approval = relationship(
        "Approval",
        back_populates="task_links",
    )

    def __repr__(self) -> str:
        return f"<TaskApprovalLink " f"task={self.task_id} " f"approval={self.approval_id}>"
