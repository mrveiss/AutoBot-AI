# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC work item SQLAlchemy models (GH#8213, GH#8230).

Covers the full work item hierarchy: Epic → Feature → PBI → Task/Bug/Subtask/Spike/Risk.
A single ``llc_work_items`` table with a ``type`` discriminator column avoids
hierarchy-specific tables and simplifies queries across the entire backlog.

Atomic checkout uses ``checkout_run_id`` / ``checkout_locked_at`` at the DB layer
(SELECT … FOR UPDATE) combined with a Redis SET NX EX 1800 fence to prevent
double-assignment across workers.

Co-working (GH#8230): any work item may have a secondary co-worker alongside the
primary assignee. The co_working_enabled flag gates the feature; co_worker_type /
co_worker_agent_id / co_worker_user_id identify the co-worker. Primary checkout
invariants are unchanged — only the primary assignee holds the checkout lock.
"""

import uuid
from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user_management.models.base import Base

from .enums import WorkItemPriority, WorkItemRelationType, WorkItemStatus, WorkItemType, pg_enum_values


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
        sa.Enum(WorkItemType, name="workitemtype", create_type=False, values_callable=pg_enum_values),
        nullable=False,
    )

    # Identity
    identifier: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acceptance_criteria: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    labels: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))

    # GitHub PR linking (GH#9625)
    linked_pr_urls: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sa.text("'[]'::jsonb"),
    )

    # Status / priority
    status: Mapped[str] = mapped_column(
        sa.Enum(WorkItemStatus, name="workitemstatus", create_type=False, values_callable=pg_enum_values),
        nullable=False,
        server_default=WorkItemStatus.BACKLOG.value,
        index=True,
    )
    priority: Mapped[str] = mapped_column(
        sa.Enum(WorkItemPriority, name="workitempriority", create_type=False, values_callable=pg_enum_values),
        nullable=False,
        server_default=WorkItemPriority.MEDIUM.value,
        index=True,
    )
    story_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    backlog_position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    needs_triage: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="false")

    # Assignment — primary
    assignee_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    assignee_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    assignee_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    # Co-working — secondary (GH#8230)
    co_worker_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    co_worker_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    co_worker_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    co_working_enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="false")

    # Atomic checkout lock fields
    checkout_run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checkout_locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Free-text intent supplied at checkout time — audit trail (GH#9532)
    checkout_intent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Optimistic concurrency version counter
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    # Audit: who created this item
    created_by_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Review / handoff fields (GH#8231, GH#8232)
    reviewer_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    reviewer_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    review_brief: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Planned schedule for Gantt/timeline view (GH#9020) — distinct from the
    # actual started_at/completed_at timestamps below.
    scheduled_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

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
    work_products: Mapped[List["LLCWorkProduct"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "LLCWorkProduct",
        back_populates="work_item",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    outgoing_relations: Mapped[List["LLCWorkItemRelation"]] = relationship(
        "LLCWorkItemRelation",
        foreign_keys="LLCWorkItemRelation.source_id",
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    incoming_relations: Mapped[List["LLCWorkItemRelation"]] = relationship(
        "LLCWorkItemRelation",
        foreign_keys="LLCWorkItemRelation.target_id",
        back_populates="target",
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


class LLCWorkItemRelation(Base):
    """Directed relation between two LLC work items (GH#8252).

    Service layer ensures ``blocks`` A→B always creates a mirror ``blocked_by`` B→A.
    Removing either leg removes both.
    """

    __tablename__ = "llc_work_item_relations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_work_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_work_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation_type: Mapped[str] = mapped_column(
        sa.Enum(WorkItemRelationType, name="workitemrelationtype", create_type=False, values_callable=pg_enum_values),
        nullable=False,
    )
    created_by_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    source: Mapped["LLCWorkItem"] = relationship(
        "LLCWorkItem",
        foreign_keys=[source_id],
        back_populates="outgoing_relations",
    )
    target: Mapped["LLCWorkItem"] = relationship(
        "LLCWorkItem",
        foreign_keys=[target_id],
        back_populates="incoming_relations",
    )

    __table_args__ = (
        sa.UniqueConstraint("source_id", "target_id", "relation_type", name="uq_work_item_relation"),
        sa.CheckConstraint("source_id != target_id", name="ck_work_item_relation_no_self"),
    )
