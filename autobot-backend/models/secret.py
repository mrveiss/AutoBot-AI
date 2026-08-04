# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Secret Model for Database Storage

Implements secure secret storage with ownership, scoping, and encryption.
Part of Issue #870 - User-Centric Session Tracking (#608 Phase 1-2).
"""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from autobot_shared.scoping import Principal, ResourceDescriptor, ScopeLevel, is_visible
from autobot_shared.time_utils import now_utc
from user_management.models.base import Base

# Deprecated alias (#11290): SecretScope is now the canonical
# autobot_shared.scoping.ScopeLevel. Kept so existing imports keep working;
# new code should import ScopeLevel directly. Stored `secrets.scope` values
# (user/session/shared/group/organization/workflow) are unchanged — the
# canonical enum carries the same .value strings.
SecretScope = ScopeLevel


class SecretType(str, Enum):
    """Secret type classification."""

    SSH_KEY = "ssh_key"
    # nosemgrep: autobot-hardcoded-secret-key
    PASSWORD = "password"  # nosec B105  # enum value, not actual password
    # nosemgrep: autobot-hardcoded-secret-key
    API_KEY = "api_key"
    # nosemgrep: autobot-hardcoded-secret-key
    TOKEN = "token"  # nosec B105  # enum value, not actual token
    OAUTH_REFRESH_TOKEN = "oauth_refresh_token"  # nosec B105  # enum value
    CERTIFICATE = "certificate"
    DATABASE_URL = "database_url"
    INFRASTRUCTURE_HOST = "infrastructure_host"
    OTHER = "other"


class Secret(Base):
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
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Ownership (Issue #870, #685)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
        comment="User ID who owns this secret",
    )

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
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
        comment="Visibility scope: user, session, shared, group, organization, or workflow",
    )

    team_ids: Mapped[dict] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
        comment="Array of team IDs for group-scoped secrets (Issue #685)",
    )

    session_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
        comment="Session ID for session-scoped secrets",
    )

    # Migration 20260324_017 (Issue #2153, #9975)
    workflow_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
        comment="Workflow ID for workflow-scoped secrets (Issue #2153). Set when scope='workflow'.",
    )

    shared_with: Mapped[dict] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
        comment="Array of user IDs for shared secrets",
    )

    # Encrypted storage (Issue #870). Legacy Fernet path — nullable since the
    # unified envelope store (#10088) holds the value in ``sealed_value``
    # instead. A row is envelope-backed iff ``sealed_value IS NOT NULL``.
    encrypted_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Fernet-encrypted secret value (legacy path; NULL for envelope rows)",
    )

    # Unified envelope store (umbrella #10088). The value is sealed once under a
    # per-secret DEK; the DEK is wrapped per grantee vault in ``secret_grants``.
    owner_vault: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        index=True,
        comment="VaultRef.to_str() of the owning vault (envelope store). NULL for legacy rows.",
    )

    sealed_value: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="SealedSecret.to_dict() — envelope-sealed value (#10088); NULL for legacy rows.",
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
        comment="Envelope DEK/rotation generation (#10088).",
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    tags: Mapped[dict] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
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
        return f"<Secret(id={self.id}, name={self.name}, " f"owner_id={self.owner_id}, scope={self.scope})>"

    @property
    def is_expired(self) -> bool:
        """Check if secret has expired."""
        if self.expires_at is None:
            return False
        return now_utc() > self.expires_at

    def _grant_lookup(self, user_id: uuid.UUID, session_id: str | None) -> bool:
        """Secrets grant facts for ``is_visible`` (#11290).

        Models the two subsystem-specific grant tables: session binding
        (session-scoped secrets are bound to the session, not the user) and
        the explicit ``shared_with`` list.
        """
        if self.scope == SecretScope.SESSION.value:
            return self.session_id == session_id
        if self.scope == SecretScope.SHARED.value:
            shared_list = self.shared_with if isinstance(self.shared_with, list) else []
            return str(user_id) in shared_list
        return False

    def is_accessible_by(
        self,
        user_id: uuid.UUID,
        session_id: str | None = None,
        user_org_id: uuid.UUID | None = None,
        user_team_ids: list | None = None,
    ) -> bool:
        """
        Check if user can access this secret.

        Issue #685: Added org and team-based access control.
        Issue #11290: thin adapter over the canonical
        ``autobot_shared.scoping.is_visible`` primitive — owner, org, and
        team rules delegate to the shared rule; session-match and
        ``shared_with`` semantics are modeled as this subsystem's grant
        lookup (``_grant_lookup``).

        Args:
            user_id: User requesting access
            session_id: Session context (required for session-scoped secrets)
            user_org_id: User's organization ID
            user_team_ids: List of team IDs user belongs to

        Returns:
            True if user has access, False otherwise
        """
        principal = Principal(
            user_id=str(user_id),
            company_id=str(user_org_id) if user_org_id else None,
            group_ids=frozenset(str(team_id) for team_id in (user_team_ids or [])),
        )
        try:
            scope = ScopeLevel(self.scope)
        except ValueError:
            scope = ScopeLevel.USER  # unknown stored scope: fail closed (owner-only)
        secret_teams = self.team_ids if isinstance(self.team_ids, list) else []
        resource = ResourceDescriptor(
            owner_id=str(self.owner_id),
            company_id=str(self.org_id) if self.org_id else None,
            scope=scope,
            # keep the stored-value comparison semantics: only string entries
            # can ever match ``str(team_id)`` membership checks
            group_ids=frozenset(t for t in secret_teams if isinstance(t, str)),
        )
        return is_visible(principal, resource, lambda: self._grant_lookup(user_id, session_id))

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
