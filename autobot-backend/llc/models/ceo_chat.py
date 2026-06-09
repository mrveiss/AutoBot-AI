# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC CEO Chat SQLAlchemy models (GH#8233).

Two tables:
  llc_ceo_chat_threads  — one thread per decision/conversation
  llc_ceo_chat_messages — ordered messages within a thread

Every thread optionally stores the work object it resolved to via
``resolved_entity_type`` / ``resolved_entity_id`` once the LLM response
has been interpreted and the appropriate LLC service has been called.
"""

import uuid
from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user_management.models.base import Base


class LLCCeoChatThread(Base):
    """One CEO Chat thread — scoped to a company, resolves to a work object."""

    __tablename__ = "llc_ceo_chat_threads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)

    # Nullable until the LLM resolves the thread to a concrete work object.
    resolved_entity_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
        onupdate=sa.text("now()"),
    )

    messages: Mapped[List["LLCCeoChatMessage"]] = relationship(
        "LLCCeoChatMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="LLCCeoChatMessage.created_at",
        lazy="selectin",
    )


class LLCCeoChatMessage(Base):
    """One message in a CEO Chat thread."""

    __tablename__ = "llc_ceo_chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_ceo_chat_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "human" = board/user message; "system" = LLM/service reply
    author_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    author_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    thread: Mapped["LLCCeoChatThread"] = relationship(
        "LLCCeoChatThread",
        back_populates="messages",
    )


__all__ = ["LLCCeoChatMessage", "LLCCeoChatThread"]
