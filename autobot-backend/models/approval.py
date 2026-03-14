# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Approval Gate Models (#1402)

SQLAlchemy models for human-in-the-loop approval gates.
"""

import uuid
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from user_management.models.base import Base, TimestampMixin


class ApprovalStatus(str, Enum):
    """Possible statuses for an approval gate."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"


class ApprovalType(str, Enum):
    """Categories of approval gates."""

    DESTRUCTIVE_ACTION = "destructive_action"
    RESOURCE_REQUEST = "resource_request"
    CREATE_AGENT = "create_agent"
    WORKFLOW_GATE = "workflow_gate"


class Approval(Base, TimestampMixin):
    """A human-in-the-loop approval gate request (#1402)."""

    __tablename__ = "approvals"

    id = Column(
        UUID(as_uuid=True),
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
    decided_at = Column(DateTime, nullable=True)

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
        return (
            f"<Approval id={self.id} "
            f"type={self.approval_type} "
            f"status={self.status}>"
        )


class ApprovalComment(Base, TimestampMixin):
    """A comment on an approval gate (#1402)."""

    __tablename__ = "approval_comments"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    approval_id = Column(
        UUID(as_uuid=True),
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
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    approval_id = Column(
        UUID(as_uuid=True),
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
        return (
            f"<TaskApprovalLink "
            f"task={self.task_id} "
            f"approval={self.approval_id}>"
        )
