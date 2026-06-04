# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ChatSharedLink model for public shared conversation links (GH#8996).

Stores tokenized public links for chat sessions with optional password
protection, expiry, and revoke support.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
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
