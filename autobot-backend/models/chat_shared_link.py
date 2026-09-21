# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ChatSharedLink model for public shared conversation links (GH#8996).

Stores tokenized public links for chat sessions with optional password
protection, expiry, and revoke support.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from autobot_shared.time_utils import now_utc
from user_management.models.base import Base


class ChatSharedLink(Base):
    """Public shareable link for a chat session.

    Attributes:
        id: UUID primary key
        session_id: Chat session being shared
        token: URL-safe unique token (URL path component)
        password_hash: Optional bcrypt hash; None means no password required
        expires_at: Optional expiry timestamp; None means no expiry
        created_by: Username or user ID of the link creator
        is_active: False after the link is revoked
        created_at: Creation timestamp
        view_count: Number of times the link has been accessed (#16861)
        last_accessed_at: Timestamp of the last access; None if never accessed (#16861)
        require_login: If True, only authenticated users can access (#16861)
    """

    __tablename__ = "chat_shared_links"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    session_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    password_hash: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="bcrypt hash; NULL means no password required",
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )

    view_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        server_default="0",
        comment="Number of times this link has been accessed",
    )

    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the last access; NULL if never accessed",
    )

    require_login: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
        comment="If True, only authenticated users can access (no public access)",
    )

    @property
    def is_expired(self) -> bool:
        """True when expires_at is set and in the past."""
        if self.expires_at is None:
            return False
        return now_utc() > self.expires_at

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    def __repr__(self) -> str:
        return (
            f"<ChatSharedLink(id={self.id}, session_id={self.session_id}, "
            f"token={self.token[:8]}…, active={self.is_active})>"
        )
