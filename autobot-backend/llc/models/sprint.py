# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLCSprint model — leaf of Portfolio → Program → Project → Sprint (GH#8219)."""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user_management.models.base import Base

from .enums import SprintStatus


class LLCSprint(Base):
    """Sprint belongs to a project (GH#8219).

    ``capacity_points`` is planned story-point budget; ``velocity_actual``
    is updated at close time with the actual points delivered.
    """

    __tablename__ = "llc_sprints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SprintStatus.PLANNING.value, index=True
    )
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    capacity_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    velocity_actual: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("now()"),
        onupdate=sa.text("now()"),
        nullable=False,
    )

    project: Mapped["LLCProject"] = relationship(  # noqa: F821
        "LLCProject", back_populates="sprints", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<LLCSprint id={self.id!r} name={self.name!r} status={self.status!r}>"
