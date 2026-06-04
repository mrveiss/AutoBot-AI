# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC Routine SQLAlchemy models (GH#8229).

A Routine is a recurring agent task defined by a cron schedule. Each time the
scheduler fires a routine it creates an LLCRoutineRun record and dispatches
the agent via the existing heartbeat pipeline.

Design decisions:
- env is JSONB nullable: overlay order (agent_env < project_env < routine_env)
  is enforced by RoutineService.resolve_env(), not stored as a computed column.
- status uses RoutineStatus enum; only ACTIVE routines are loaded by the scheduler.
- soft-delete: DELETE sets status=ARCHIVED, never removes the row.
- produces controls whether a run creates a new work item or updates a recurring one.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user_management.models.base import Base

from .enums import RoutineProduces, RoutineStatus


class LLCRoutine(Base):
    """Recurring agent task (GH#8229)."""

    __tablename__ = "llc_routines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    cron_schedule: Mapped[str] = mapped_column(sa.Text, nullable=False)
    assignee_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        server_default=RoutineStatus.ACTIVE.value,
    )
    env: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    produces: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        server_default=RoutineProduces.NEW_WORK_ITEM.value,
    )
    work_item_template: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    recurring_work_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("llc_work_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_fired_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    runs: Mapped[List["LLCRoutineRun"]] = relationship(
        "LLCRoutineRun",
        back_populates="routine",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<LLCRoutine(id={self.id}, name={self.name!r}, status={self.status})>"


class LLCRoutineRun(Base):
    """Record of a single routine execution (GH#8229)."""

    __tablename__ = "llc_routine_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    routine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("llc_routines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    heartbeat_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("llc_heartbeat_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    work_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("llc_work_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="queued")
    started_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    routine: Mapped["LLCRoutine"] = relationship("LLCRoutine", back_populates="runs")

    def __repr__(self) -> str:
        return f"<LLCRoutineRun(id={self.id}, routine_id={self.routine_id}, status={self.status})>"
