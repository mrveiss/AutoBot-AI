# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC board SQLAlchemy models (GH#8221).

Two tables:
  llc_boards       — one row per Kanban or Sprint board.
  llc_board_columns — ordered columns that belong to a board.

``status_filter`` is a JSONB array of WorkItemStatus string values.  When a
work item is moved into a column the first value in the array becomes the new
work item status (via WorkItemService.transition_status).

Both project_id and sprint_id are stored as plain UUIDs without FK constraints:
the project and sprint tables live in separate GH issues (#8220 / #8219) and
will be FK-linked once those land.
"""

import uuid
from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user_management.models.base import Base

from .enums import BoardType


class LLCBoard(Base):
    """A Kanban or Sprint board belonging to a company."""

    __tablename__ = "llc_boards"
    __table_args__ = (
        sa.UniqueConstraint("company_id", "project_id", "type", name="uq_llc_boards_company_project_type"),
        sa.UniqueConstraint("company_id", "sprint_id", "type", name="uq_llc_boards_company_sprint_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    sprint_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    type: Mapped[str] = mapped_column(
        sa.Enum(BoardType, name="boardtype", create_type=False),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    columns: Mapped[List["LLCBoardColumn"]] = relationship(
        "LLCBoardColumn",
        back_populates="board",
        order_by="LLCBoardColumn.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class LLCBoardColumn(Base):
    """An ordered column within an LLC board."""

    __tablename__ = "llc_board_columns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    board_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_boards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # JSON array of WorkItemStatus values that map into this column.
    status_filter: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    wip_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    board: Mapped["LLCBoard"] = relationship("LLCBoard", back_populates="columns")
