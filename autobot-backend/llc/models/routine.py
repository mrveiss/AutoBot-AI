# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC Routine SQLAlchemy model (GH#8229).

A Routine is a recurring agent task defined by a cron schedule. Each time the
scheduler fires a routine it creates an LLCRoutineRun record and dispatches
the agent via the existing heartbeat pipeline.

Design decisions:
- env is JSONB: overlay order (agent_env < project_env < routine_env < system_keys)
  is enforced by RoutineService.resolve_env(), not stored as a computed column.
- status uses RoutineStatus enum; only ACTIVE routines are loaded by the scheduler.
- soft-delete: DELETE sets status=ARCHIVED, never removes the row.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base

from .enums import RoutineStatus


class LLCRoutine(Base):
    """Recurring agent task (GH#8229)."""

    __tablename__ = "llc_routines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    cron_schedule: Mapped[str] = mapped_column(
        sa.String(100), nullable=False, comment="Standard 5-field cron expression"
    )
    env: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        comment="Routine-level env overlay; merged over agent_env by RoutineService",
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(RoutineStatus, name="routinestatus", create_type=False),
        nullable=False,
        server_default=RoutineStatus.ACTIVE.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
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
    status: Mapped[str] = mapped_column(
        sa.Enum("queued", "running", "completed", "failed", name="routinerunstatus", create_type=False),
        nullable=False,
        server_default="queued",
    )
    triggered_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)

    def __repr__(self) -> str:
        return f"<LLCRoutineRun(id={self.id}, routine_id={self.routine_id}, status={self.status})>"
