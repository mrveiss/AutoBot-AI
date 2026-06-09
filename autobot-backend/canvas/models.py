# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
SQLAlchemy 2.0 ORM models for Live Canvas (MVA-359).

Schema is forward-compatible for Phase 3 multi-user: version + locked_by
are present from day 1. No concurrency layer is enforced in Phase 1.
"""

import enum
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class CellState(str, enum.Enum):
    queued = "queued"
    skeleton = "skeleton"
    streaming = "streaming"
    complete = "complete"
    committed = "committed"
    error = "error"
    cancelled = "cancelled"


class CellOwner(str, enum.Enum):
    agent = "agent"
    user = "user"


class CellType(str, enum.Enum):
    text = "text"
    code = "code"
    chart = "chart"
    image = "image"


class UndoEventType(str, enum.Enum):
    cell_add = "cell_add"
    cell_edit = "cell_edit"
    cell_delete = "cell_delete"
    cell_accept = "cell_accept"
    cell_discard = "cell_discard"


class Canvas(Base):
    __tablename__ = "canvas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(sa.String(512), nullable=False, default="Untitled Canvas")
    save_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    undo_cursor: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")


class CanvasCell(Base):
    __tablename__ = "canvas_cell"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("canvas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    type: Mapped[str] = mapped_column(sa.String(50), nullable=False, server_default="text")
    content: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="")
    state: Mapped[str] = mapped_column(sa.String(50), nullable=False, server_default="committed")
    owner: Mapped[str] = mapped_column(sa.String(50), nullable=False, server_default="user")
    # Phase 3 forward-compat: present from day 1, not enforced in Phase 1
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    locked_by: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    # Phase 2: rich payload for chart/code cells — null for Phase 1 clients (additive)
    rich_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class CanvasUndoEvent(Base):
    __tablename__ = "canvas_undo_event"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("canvas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
