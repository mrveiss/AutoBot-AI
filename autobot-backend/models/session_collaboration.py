# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Session Collaboration Model

Implements multi-user collaboration for chat sessions with permission levels.
Part of Issue #872 - Session Collaboration API (#608 Phase 3).
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from user_management.models.base import Base, TimestampMixin


class PermissionLevel(str, Enum):
    """Collaboration permission levels."""

    OWNER = "owner"  # Full control (invite, remove, modify, delete)
    EDITOR = "editor"  # Can modify session and secrets
    VIEWER = "viewer"  # Read-only access


class SessionCollaboration(Base, TimestampMixin):
    """
    Session collaboration model with owner and multi-user permissions.

    Attributes:
        session_id: Chat session identifier
        owner_id: User ID who owns the session
        collaborators: JSONB dict mapping user_id -> permission_level
        invitations: JSONB array of pending invitations
        collaboration_metadata: Additional collaboration metadata
    """

    __tablename__ = "session_collaborations"

    session_id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
        nullable=False,
        index=True,
        comment="Chat session identifier",
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID who owns the session",
    )

    # Collaborators: {user_id: permission_level}
    collaborators: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        comment="Map of user_id to permission_level (owner/editor/viewer)",
    )

    # Pending invitations: [{user_id, permission, invited_at, expires_at}]
    invitations: Mapped[dict] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
        comment="Pending collaboration invitations",
    )

    collaboration_metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        comment="Additional collaboration metadata",
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<SessionCollaboration(session_id={self.session_id}, "
            f"owner_id={self.owner_id}, "
            f"collaborators={len(self.collaborators)})>"
        )

    def get_permission(self, user_id: uuid.UUID) -> Optional[str]:
        """
        Get user's permission level for this session.

        Args:
            user_id: User requesting access

        Returns:
            Permission level string or None if no access
        """
        # Owner has owner permission
        if self.owner_id == user_id:
            return PermissionLevel.OWNER.value

        # Check collaborators
        user_id_str = str(user_id)
        collaborators_dict = (
            self.collaborators if isinstance(self.collaborators, dict) else {}
        )
        return collaborators_dict.get(user_id_str)

    def has_permission(
        self, user_id: uuid.UUID, required_level: PermissionLevel
    ) -> bool:
        """
        Check if user has at least the required permission level.

        Permission hierarchy: owner > editor > viewer

        Args:
            user_id: User to check
            required_level: Minimum required permission

        Returns:
            True if user has sufficient permission
        """
        user_perm = self.get_permission(user_id)
        if user_perm is None:
            return False

        # Permission hierarchy
        levels = {
            PermissionLevel.VIEWER.value: 1,
            PermissionLevel.EDITOR.value: 2,
            PermissionLevel.OWNER.value: 3,
        }

        user_level = levels.get(user_perm, 0)
        required = levels.get(required_level.value, 999)

        return user_level >= required

    def add_collaborator(self, user_id: uuid.UUID, permission: PermissionLevel) -> None:
        """
        Add or update collaborator permission.

        Args:
            user_id: User to add
            permission: Permission level to grant
        """
        collaborators_dict = (
            self.collaborators if isinstance(self.collaborators, dict) else {}
        )
        collaborators_dict[str(user_id)] = permission.value
        self.collaborators = collaborators_dict

    def remove_collaborator(self, user_id: uuid.UUID) -> bool:
        """
        Remove collaborator from session.

        Args:
            user_id: User to remove

        Returns:
            True if removed, False if not found
        """
        collaborators_dict = (
            self.collaborators if isinstance(self.collaborators, dict) else {}
        )
        user_id_str = str(user_id)

        if user_id_str in collaborators_dict:
            del collaborators_dict[user_id_str]
            self.collaborators = collaborators_dict
            return True

        return False

    def list_collaborators(self) -> dict:
        """
        Get all collaborators with permissions.

        Returns:
            Dict mapping user_id -> permission_level
        """
        return self.collaborators if isinstance(self.collaborators, dict) else {}

    def add_invitation(
        self,
        user_id: uuid.UUID,
        permission: PermissionLevel,
        expires_at: Optional[datetime] = None,
    ) -> None:
        """
        Add pending invitation.

        Args:
            user_id: User to invite
            permission: Permission level for invitation
            expires_at: Optional expiration timestamp
        """
        invitations_list = (
            self.invitations if isinstance(self.invitations, list) else []
        )

        # Remove existing invitation for this user
        invitations_list = [
            inv for inv in invitations_list if inv.get("user_id") != str(user_id)
        ]

        invitation = {
            "user_id": str(user_id),
            "permission": permission.value,
            "invited_at": datetime.utcnow().isoformat(),
        }

        if expires_at:
            invitation["expires_at"] = expires_at.isoformat()

        invitations_list.append(invitation)
        self.invitations = invitations_list

    def remove_invitation(self, user_id: uuid.UUID) -> bool:
        """
        Remove pending invitation.

        Args:
            user_id: User invitation to remove

        Returns:
            True if removed, False if not found
        """
        invitations_list = (
            self.invitations if isinstance(self.invitations, list) else []
        )
        user_id_str = str(user_id)

        original_len = len(invitations_list)
        invitations_list = [
            inv for inv in invitations_list if inv.get("user_id") != user_id_str
        ]

        if len(invitations_list) < original_len:
            self.invitations = invitations_list
            return True

        return False
