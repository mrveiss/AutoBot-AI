# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Secret Model for Database Storage

Implements secure secret storage with ownership, scoping, and encryption.
Part of Issue #870 - User-Centric Session Tracking (#608 Phase 1-2).
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from user_management.models.base import Base, TimestampMixin


class SecretScope(str, Enum):
    """Secret visibility scope.

    Issue #685: Aligned with knowledge VisibilityLevel for consistency.
    """

    USER = "user"  # Only accessible by owner (private)
    SESSION = "session"  # Only accessible in specific session
    SHARED = "shared"  # Explicitly shared with specific users
    GROUP = "group"  # Accessible to team members
    ORGANIZATION = "organization"  # Accessible to all org members


class SecretType(str, Enum):
    """Secret type classification."""

    SSH_KEY = "ssh_key"
    PASSWORD = "password"  # nosec B105 - enum value, not actual password
    API_KEY = "api_key"
    TOKEN = "token"  # nosec B105 - enum value, not actual token
    CERTIFICATE = "certificate"
    DATABASE_URL = "database_url"
    INFRASTRUCTURE_HOST = "infrastructure_host"
    OTHER = "other"


class Secret(Base, TimestampMixin):
    """
    Secret model with ownership and scoping.

    Attributes:
        id: Unique identifier (UUID)
        owner_id: User ID who owns this secret
        name: Secret name/identifier
        type: Secret type classification
        scope: Visibility scope (user/session/shared)
        session_id: Session ID for session-scoped secrets
        shared_with: JSON array of user IDs for shared secrets
        encrypted_value: Fernet-encrypted secret value
        description: Optional description
        tags: JSON array of tags for categorization
        expires_at: Optional expiration timestamp
        is_active: Whether secret is active/valid
        metadata: Additional metadata (JSONB)
    """

    __tablename__ = "secrets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Ownership (Issue #870, #685)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="User ID who owns this secret",
    )

    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Organization ID for org-level secrets (Issue #685)",
    )

    # Secret identity
    name: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        index=True,
    )

    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Scoping (Issue #870, #685)
    scope: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SecretScope.USER.value,
        index=True,
        comment="Visibility scope: user, session, shared, group, or organization",
    )

    team_ids: Mapped[dict] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
        comment="Array of team IDs for group-scoped secrets (Issue #685)",
    )

    session_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        index=True,
        comment="Session ID for session-scoped secrets",
    )

    shared_with: Mapped[dict] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
        comment="Array of user IDs for shared secrets",
    )

    # Encrypted storage (Issue #870)
    encrypted_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Fernet-encrypted secret value",
    )

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
    )

    tags: Mapped[dict] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    extra_data: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<Secret(id={self.id}, name={self.name}, "
            f"owner_id={self.owner_id}, scope={self.scope})>"
        )

    @property
    def is_expired(self) -> bool:
        """Check if secret has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def is_accessible_by(
        self,
        user_id: uuid.UUID,
        session_id: Optional[str] = None,
        user_org_id: Optional[uuid.UUID] = None,
        user_team_ids: Optional[list] = None,
    ) -> bool:
        """
        Check if user can access this secret.

        Issue #685: Added org and team-based access control.

        Args:
            user_id: User requesting access
            session_id: Session context (required for session-scoped secrets)
            user_org_id: User's organization ID
            user_team_ids: List of team IDs user belongs to

        Returns:
            True if user has access, False otherwise
        """
        user_team_ids = user_team_ids or []

        # Owner always has access
        if self.owner_id == user_id:
            return True

        # Session-scoped requires matching session
        if self.scope == SecretScope.SESSION.value:
            return self.session_id == session_id

        # Organization-scoped: accessible to all org members
        if self.scope == SecretScope.ORGANIZATION.value:
            return user_org_id and self.org_id == user_org_id

        # Group-scoped: accessible to team members
        if self.scope == SecretScope.GROUP.value:
            secret_teams = self.team_ids if isinstance(self.team_ids, list) else []
            return any(str(team_id) in secret_teams for team_id in user_team_ids)

        # Shared secrets check shared_with list
        if self.scope == SecretScope.SHARED.value:
            shared_list = self.shared_with if isinstance(self.shared_with, list) else []
            return str(user_id) in shared_list

        # User-scoped is only accessible by owner
        return False

    def share_with(self, user_id: uuid.UUID) -> None:
        """
        Share secret with another user.

        Args:
            user_id: User ID to share with
        """
        if self.scope != SecretScope.SHARED.value:
            self.scope = SecretScope.SHARED.value

        shared_list = self.shared_with if isinstance(self.shared_with, list) else []
        user_id_str = str(user_id)

        if user_id_str not in shared_list:
            shared_list.append(user_id_str)
            self.shared_with = shared_list

    def unshare_with(self, user_id: uuid.UUID) -> None:
        """
        Remove user from shared access.

        Args:
            user_id: User ID to remove
        """
        shared_list = self.shared_with if isinstance(self.shared_with, list) else []
        user_id_str = str(user_id)

        if user_id_str in shared_list:
            shared_list.remove(user_id_str)
            self.shared_with = shared_list

    def deactivate(self) -> None:
        """Deactivate the secret."""
        self.is_active = False

    def activate(self) -> None:
        """Activate the secret."""
        self.is_active = True
