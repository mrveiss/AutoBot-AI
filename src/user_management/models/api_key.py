# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
API Key Model

Long-lived API keys for programmatic access.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.user_management.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.user_management.models.user import User
    from src.user_management.models.team import Team


class APIKey(Base, TimestampMixin):
    """
    API Key model.

    Attributes:
        id: Unique identifier (UUID)
        key_hash: SHA256 hash of the API key (for validation)
        key_prefix: First 12 characters of key (for identification)
        user_id: Owner of the key
        team_id: Optional team scope
        name: Human-readable name
        scopes: List of allowed scopes/permissions
        expires_at: Optional expiration time
        last_used_at: Last usage timestamp
    """

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # SHA256 hash of the full key
    key_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    # First 12 chars for identification (e.g., "abot_abc123...")
    key_prefix: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        index=True,
    )

    # Owner (always required)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional team scope
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Human-readable name
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Description
    description: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    # Scopes/permissions this key grants
    scopes: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Expiration (nullable = never expires)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Usage tracking
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    usage_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Revocation info
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="api_keys",
        foreign_keys=[user_id],
    )

    team: Mapped[Optional["Team"]] = relationship(
        "Team",
        back_populates="api_keys",
    )

    def __repr__(self) -> str:
        return f"<APIKey(prefix={self.key_prefix}, name={self.name}, user_id={self.user_id})>"

    @property
    def is_expired(self) -> bool:
        """Check if the key has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def is_revoked(self) -> bool:
        """Check if the key has been revoked."""
        return self.revoked_at is not None

    @property
    def is_valid(self) -> bool:
        """Check if the key is valid (active, not expired, not revoked)."""
        return self.is_active and not self.is_expired and not self.is_revoked

    def record_usage(self) -> None:
        """Record a usage of this API key."""
        self.last_used_at = datetime.utcnow()
        self.usage_count += 1

    def revoke(self, revoked_by_user_id: Optional[uuid.UUID] = None) -> None:
        """Revoke the API key."""
        self.is_active = False
        self.revoked_at = datetime.utcnow()
        self.revoked_by = revoked_by_user_id

    def has_scope(self, scope: str) -> bool:
        """Check if this key has a specific scope."""
        # Check exact match
        if scope in self.scopes:
            return True

        # Check wildcard (e.g., "chat:*" matches "chat:use")
        resource = scope.split(":")[0] if ":" in scope else scope
        wildcard = f"{resource}:*"
        if wildcard in self.scopes:
            return True

        # Check global admin scope
        if "*" in self.scopes or "admin:*" in self.scopes:
            return True

        return False


# Available API key scopes
API_KEY_SCOPES = {
    # Chat
    "chat:use": "Send and receive chat messages",
    "chat:history": "Read chat history",
    # Knowledge
    "knowledge:read": "Read knowledge base entries",
    "knowledge:write": "Create/update knowledge entries",
    "knowledge:delete": "Delete knowledge entries",
    # Files
    "files:read": "Read/download files",
    "files:write": "Upload/update files",
    "files:delete": "Delete files",
    # Users (admin)
    "users:read": "Read user information",
    "users:write": "Create/update users",
    # Settings
    "settings:read": "Read application settings",
    "settings:write": "Modify settings",
    # Webhooks
    "webhooks:trigger": "Trigger webhook events",
    # Admin
    "admin:*": "Full administrative access",
}
