# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC sprint hierarchy models — Portfolio → Program → Project → Sprint (GH#8219).

Tables:
  llc_portfolios  — top-level collection of programs
  llc_programs    — collection of projects within a portfolio
  llc_projects    — collection of sprints within a program
  llc_sprints     — time-boxed unit of work items

``work_items.project_id`` and ``work_items.sprint_id`` FKs are added by
migration 20260523_030 after these tables exist.
"""

import uuid
from datetime import date, datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base

from .enums import SprintStatus


class LLCPortfolio(Base):
    """Top-level grouping of programs (GH#8219)."""

    __tablename__ = "llc_portfolios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.Enum("active", "paused", "archived", name="portfoliostatus", create_type=True),
        nullable=False,
        server_default="active",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    def __repr__(self) -> str:
        return f"<LLCPortfolio id={self.id!r} name={self.name!r}>"


class LLCProgram(Base):
    """Collection of projects within a portfolio (GH#8219)."""

    __tablename__ = "llc_programs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    portfolio_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_portfolios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.Enum("active", "paused", "archived", name="programstatus", create_type=True),
        nullable=False,
        server_default="active",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    def __repr__(self) -> str:
        return f"<LLCProgram id={self.id!r} name={self.name!r}>"


class LLCProject(Base):
    """Project that owns a sequence of sprints (GH#8219)."""

    __tablename__ = "llc_projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    program_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_programs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    goal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_goals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.Enum(
            "backlog",
            "planned",
            "in_progress",
            "completed",
            "cancelled",
            name="projectstatus",
            create_type=True,
        ),
        nullable=False,
        server_default="backlog",
        index=True,
    )
    lead_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    lead_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    env: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Per-project rollover behaviour (overrides company default when set).
    auto_rollover: Mapped[Optional[bool]] = mapped_column(sa.Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    def __repr__(self) -> str:
        return f"<LLCProject id={self.id!r} name={self.name!r}>"


class LLCSprint(Base):
    """Time-boxed unit of work items within a project (GH#8219).

    Closing a sprint requires board approval (ApprovalType.SPRINT_CLOSE).
    Once approved, SprintAutoCloseService handles:
      1. status → closed, actual_points computed
      2. KB summarization (stub until Phase 5)
      3. Incomplete item rollover
    """

    __tablename__ = "llc_sprints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    goal_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        sa.Enum(SprintStatus, name="sprintstatus", create_type=False),
        nullable=False,
        server_default=SprintStatus.PLANNING.value,
        index=True,
    )
    committed_points: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    actual_points: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    velocity_actual: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    capacity_points: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    projection: Mapped[Optional[float]] = mapped_column(sa.Numeric(10, 2), nullable=True)
    # Stores the approval_id once a sprint_close gate is requested.
    pending_close_approval_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    # LLM-generated KB summary stored on sprint close (GH#8238).
    kb_summary: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    def __repr__(self) -> str:
        return f"<LLCSprint id={self.id!r} name={self.name!r} status={self.status!r}>"


__all__ = ["LLCPortfolio", "LLCProgram", "LLCProject", "LLCSprint"]
