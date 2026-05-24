"""LLC work item SQLAlchemy models (GH#8213).

Covers the full work item hierarchy: Epic → Feature → PBI → Task/Bug/Subtask/Spike/Risk.
A single ``llc_work_items`` table with a ``type`` discriminator column avoids
hierarchy-specific tables and simplifies queries across the entire backlog.

Atomic checkout uses ``checkout_run_id`` / ``checkout_locked_at`` at the DB layer
(SELECT … FOR UPDATE) combined with a Redis SET NX EX 1800 fence to prevent
double-assignment across workers.
"""

import uuid
from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user_management.models.base import Base

from .enums import WorkItemPriority, WorkItemStatus, WorkItemType


class LLCWorkItem(Base):
    """Unified work item row — type discriminator covers all hierarchy levels."""

    __tablename__ = "llc_work_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    sprint_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    goal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_goals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_work_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Hierarchy discriminator
    type: Mapped[str] = mapped_column(
        sa.Enum(WorkItemType, name="workitemtype", create_type=False),
        nullable=False,
    )

    # Identity
    identifier: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acceptance_criteria: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    labels: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))

    # Status / priority
    status: Mapped[str] = mapped_column(
        sa.Enum(WorkItemStatus, name="workitemstatus", create_type=False),
        nullable=False,
        server_default=WorkItemStatus.BACKLOG.value,
        index=True,
    )
    priority: Mapped[str] = mapped_column(
        sa.Enum(WorkItemPriority, name="workitempriority", create_type=False),
        nullable=False,
        server_default=WorkItemPriority.MEDIUM.value,
        index=True,
    )
    story_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    backlog_position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    needs_triage: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="false")

    # Assignment
    assignee_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    assignee_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    assignee_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    # Atomic checkout lock fields
    checkout_run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checkout_locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Optimistic concurrency version counter
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    # Audit: who created this item
    created_by_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Handoff context (GH#8232): written by HandoffService.human_to_agent()
    review_brief: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Lifecycle timestamps
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Self-referencing relationship for child items
    children: Mapped[List["LLCWorkItem"]] = relationship(
        "LLCWorkItem",
        foreign_keys=[parent_id],
        back_populates="parent",
        lazy="selectin",
    )
    parent: Mapped[Optional["LLCWorkItem"]] = relationship(
        "LLCWorkItem",
        foreign_keys=[parent_id],
        back_populates="children",
        remote_side=[id],
    )

    comments: Mapped[List["LLCWorkItemComment"]] = relationship(
        "LLCWorkItemComment",
        back_populates="work_item",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class LLCWorkItemComment(Base):
    """Comments on an LLC work item."""

    __tablename__ = "llc_work_item_comments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    work_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_work_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    author_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    work_item: Mapped["LLCWorkItem"] = relationship("LLCWorkItem", back_populates="comments")
