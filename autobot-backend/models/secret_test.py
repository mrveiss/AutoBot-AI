# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit Tests for Secret Model

Tests ownership model, scoping, and access control.
Part of Issue #870 - User-Centric Session Tracking (#608 Phase 1-2).
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.datetime_utils import datetime_now
from models.secret import Secret, SecretScope, SecretType


class TestSecretModel:
    """Test Secret model structure and properties."""

    def test_secret_creation(self):
        """Test basic secret creation."""
        owner_id = uuid.uuid4()
        secret = Secret(
            owner_id=owner_id,
            name="test-secret",
            type=SecretType.API_KEY.value,
            scope=SecretScope.USER.value,
            encrypted_value="encrypted_data",
        )

        assert secret.owner_id == owner_id
        assert secret.name == "test-secret"
        assert secret.type == SecretType.API_KEY.value
        assert secret.scope == SecretScope.USER.value
        # Python-side column default applies at INSERT, not at construction
        # (stale expectation fixed in #11290); pin the column default instead.
        assert Secret.__table__.c.is_active.default.arg is True
        assert secret.is_expired is False

    def test_secret_expiration(self):
        """Test expiration checking."""
        secret = Secret(
            owner_id=uuid.uuid4(),
            name="expired-secret",
            type=SecretType.TOKEN.value,
            scope=SecretScope.USER.value,
            encrypted_value="encrypted",
            expires_at=datetime_now() - timedelta(days=1),
        )

        assert secret.is_expired is True

        secret.expires_at = datetime_now() + timedelta(days=1)
        assert secret.is_expired is False

        secret.expires_at = None
        assert secret.is_expired is False

    def test_user_scoped_access(self):
        """Test user-scoped secret access control."""
        owner_id = uuid.uuid4()
        other_user_id = uuid.uuid4()

        secret = Secret(
            owner_id=owner_id,
            name="user-secret",
            type=SecretType.PASSWORD.value,
            scope=SecretScope.USER.value,
            encrypted_value="encrypted",
        )

        # Owner has access
        assert secret.is_accessible_by(owner_id) is True

        # Other users don't have access
        assert secret.is_accessible_by(other_user_id) is False

    def test_session_scoped_access(self):
        """Test session-scoped secret access control."""
        owner_id = uuid.uuid4()
        session_id = "session-123"

        secret = Secret(
            owner_id=owner_id,
            name="session-secret",
            type=SecretType.SSH_KEY.value,
            scope=SecretScope.SESSION.value,
            session_id=session_id,
            encrypted_value="encrypted",
        )

        # Owner has access regardless of session
        assert secret.is_accessible_by(owner_id) is True
        assert secret.is_accessible_by(owner_id, "other-session") is True

        # Non-owner in the SAME session has access (session-scoped secrets are
        # bound to the session, not the user — stale expectation fixed in #11290)
        other_user_id = uuid.uuid4()
        assert secret.is_accessible_by(other_user_id, session_id) is True
        assert secret.is_accessible_by(other_user_id, "other-session") is False

    def test_shared_secret_access(self):
        """Test shared secret access control."""
        owner_id = uuid.uuid4()
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        user_c = uuid.uuid4()

        secret = Secret(
            owner_id=owner_id,
            name="shared-secret",
            type=SecretType.CERTIFICATE.value,
            scope=SecretScope.SHARED.value,
            encrypted_value="encrypted",
            shared_with=[str(user_a), str(user_b)],
        )

        # Owner has access
        assert secret.is_accessible_by(owner_id) is True

        # Shared users have access
        assert secret.is_accessible_by(user_a) is True
        assert secret.is_accessible_by(user_b) is True

        # Non-shared user doesn't have access
        assert secret.is_accessible_by(user_c) is False

    def test_share_with(self):
        """Test sharing a secret with users."""
        owner_id = uuid.uuid4()
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        secret = Secret(
            owner_id=owner_id,
            name="my-secret",
            type=SecretType.API_KEY.value,
            scope=SecretScope.USER.value,
            encrypted_value="encrypted",
        )

        # Share with user_a
        secret.share_with(user_a)

        assert secret.scope == SecretScope.SHARED.value
        assert str(user_a) in secret.shared_with
        assert secret.is_accessible_by(user_a) is True

        # Share with user_b
        secret.share_with(user_b)

        assert str(user_a) in secret.shared_with
        assert str(user_b) in secret.shared_with
        assert secret.is_accessible_by(user_b) is True

        # Sharing with same user twice doesn't duplicate
        secret.share_with(user_a)
        count = secret.shared_with.count(str(user_a))
        assert count == 1

    def test_unshare_with(self):
        """Test removing user from shared access."""
        owner_id = uuid.uuid4()
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        secret = Secret(
            owner_id=owner_id,
            name="shared-secret",
            type=SecretType.PASSWORD.value,
            scope=SecretScope.SHARED.value,
            encrypted_value="encrypted",
            shared_with=[str(user_a), str(user_b)],
        )

        # Unshare from user_a
        secret.unshare_with(user_a)

        assert str(user_a) not in secret.shared_with
        assert str(user_b) in secret.shared_with
        assert secret.is_accessible_by(user_a) is False
        assert secret.is_accessible_by(user_b) is True

    def test_activate_deactivate(self):
        """Test secret activation/deactivation."""
        secret = Secret(
            owner_id=uuid.uuid4(),
            name="test-secret",
            type=SecretType.TOKEN.value,
            scope=SecretScope.USER.value,
            encrypted_value="encrypted",
        )

        # Python-side default applies at INSERT, not construction (#11290);
        # exercise the explicit transitions only.
        secret.deactivate()
        assert secret.is_active is False

        secret.activate()
        assert secret.is_active is True

    def test_secret_repr(self):
        """Test string representation."""
        owner_id = uuid.uuid4()
        secret = Secret(
            owner_id=owner_id,
            name="test-secret",
            type=SecretType.API_KEY.value,
            scope=SecretScope.USER.value,
            encrypted_value="encrypted",
        )

        repr_str = repr(secret)
        assert "Secret" in repr_str
        assert "test-secret" in repr_str
        assert str(owner_id) in repr_str
        assert SecretScope.USER.value in repr_str


_OWNER = uuid.UUID("00000000-0000-0000-0000-000000000001")
_STRANGER = uuid.UUID("00000000-0000-0000-0000-000000000002")
_ORG = uuid.UUID("00000000-0000-0000-0000-00000000000a")
_OTHER_ORG = uuid.UUID("00000000-0000-0000-0000-00000000000b")
_TEAM = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def _secret(scope: str, **kw) -> Secret:
    base = dict(
        owner_id=_OWNER,
        name="matrix-secret",
        type=SecretType.API_KEY.value,
        scope=scope,
        encrypted_value="encrypted",
    )
    base.update(kw)
    return Secret(**base)


# Parity matrix for Secret.is_accessible_by (#11290): pins the full
# scope x principal decision table BEFORE consolidating SecretScope onto the
# canonical autobot_shared.scoping.ScopeLevel, proving the refactor is
# behavior-preserving.
# (label, secret kwargs, call kwargs, expected)
_ACCESS_MATRIX = [
    ("user_owner", _secret("user"), dict(user_id=_OWNER), True),
    ("user_stranger", _secret("user"), dict(user_id=_STRANGER), False),
    ("session_owner_any_session", _secret("session", session_id="s1"), dict(user_id=_OWNER, session_id="sX"), True),
    ("session_match", _secret("session", session_id="s1"), dict(user_id=_STRANGER, session_id="s1"), True),
    ("session_mismatch", _secret("session", session_id="s1"), dict(user_id=_STRANGER, session_id="s2"), False),
    ("session_none", _secret("session", session_id="s1"), dict(user_id=_STRANGER), False),
    # session secret with NULL session_id and no caller session currently
    # GRANTS (None == None) — pinned as-is (#11290); flagged for deliberate
    # review together with the session-match rule above.
    ("session_null_both", _secret("session"), dict(user_id=_STRANGER), True),
    (
        "shared_listed",
        _secret("shared", shared_with=[str(_STRANGER)]),
        dict(user_id=_STRANGER),
        True,
    ),
    ("shared_unlisted", _secret("shared", shared_with=["someone-else"]), dict(user_id=_STRANGER), False),
    ("shared_empty", _secret("shared", shared_with=[]), dict(user_id=_STRANGER), False),
    # non-list JSONB payloads fall back to deny for non-owners
    ("shared_nonlist_guard", _secret("shared", shared_with={"a": 1}), dict(user_id=_STRANGER), False),
    (
        "group_team_member",
        _secret("group", team_ids=[str(_TEAM)]),
        dict(user_id=_STRANGER, user_team_ids=[_TEAM]),
        True,
    ),
    (
        "group_non_member",
        _secret("group", team_ids=[str(_TEAM)]),
        dict(user_id=_STRANGER, user_team_ids=[uuid.uuid4()]),
        False,
    ),
    ("group_no_teams", _secret("group", team_ids=[str(_TEAM)]), dict(user_id=_STRANGER), False),
    # non-list JSONB payloads fall back to deny for non-owners
    (
        "group_nonlist_guard",
        _secret("group", team_ids={"a": 1}),
        dict(user_id=_STRANGER, user_team_ids=[_TEAM]),
        False,
    ),
    (
        "org_member",
        _secret("organization", org_id=_ORG),
        dict(user_id=_STRANGER, user_org_id=_ORG),
        True,
    ),
    (
        "org_other",
        _secret("organization", org_id=_ORG),
        dict(user_id=_STRANGER, user_org_id=_OTHER_ORG),
        False,
    ),
    ("org_user_no_org", _secret("organization", org_id=_ORG), dict(user_id=_STRANGER), False),
    # workflow scope: no non-owner grant path in is_accessible_by — fail closed
    ("workflow_owner", _secret("workflow", workflow_id="wf1"), dict(user_id=_OWNER), True),
    ("workflow_stranger", _secret("workflow", workflow_id="wf1"), dict(user_id=_STRANGER), False),
    # unknown stored scope value: fail closed for non-owner
    ("unknown_scope_stranger", _secret("bogus"), dict(user_id=_STRANGER), False),
    ("unknown_scope_owner", _secret("bogus"), dict(user_id=_OWNER), True),
]


class TestSecretScopeCanonicalAlias:
    """#11290: SecretScope is a thin alias of the canonical ScopeLevel."""

    def test_alias_identity(self):
        from autobot_shared.scoping import ScopeLevel

        assert SecretScope is ScopeLevel

    def test_persisted_values_unchanged(self):
        """secrets.scope stored strings must survive the consolidation."""
        assert SecretScope.USER.value == "user"
        assert SecretScope.SESSION.value == "session"
        assert SecretScope.SHARED.value == "shared"
        assert SecretScope.GROUP.value == "group"
        assert SecretScope.ORGANIZATION.value == "organization"
        assert SecretScope.WORKFLOW.value == "workflow"


class TestSecretAccessMatrix:
    """Full is_accessible_by decision table (#11290 parity guard)."""

    @pytest.mark.parametrize(
        "label,secret,call_kwargs,expected",
        _ACCESS_MATRIX,
        ids=[row[0] for row in _ACCESS_MATRIX],
    )
    def test_decision_table(self, label, secret, call_kwargs, expected):
        assert bool(secret.is_accessible_by(**call_kwargs)) is expected, label


@pytest.mark.asyncio
class TestSecretDatabase:
    """Test Secret model database operations."""

    async def test_secret_persistence(self, async_session: AsyncSession):
        """Test saving and retrieving secrets from database."""
        owner_id = uuid.uuid4()

        secret = Secret(
            owner_id=owner_id,
            name="db-test-secret",
            type=SecretType.SSH_KEY.value,
            scope=SecretScope.USER.value,
            encrypted_value="encrypted_key_data",
            description="Test SSH key",
            tags=["ssh", "production"],
        )

        async_session.add(secret)
        await async_session.commit()
        await async_session.refresh(secret)

        # Retrieve from database
        result = await async_session.execute(select(Secret).where(Secret.id == secret.id))
        retrieved_secret = result.scalar_one()

        assert retrieved_secret.id == secret.id
        assert retrieved_secret.owner_id == owner_id
        assert retrieved_secret.name == "db-test-secret"
        assert retrieved_secret.encrypted_value == "encrypted_key_data"
        assert retrieved_secret.description == "Test SSH key"
        assert "ssh" in retrieved_secret.tags
        assert "production" in retrieved_secret.tags

    async def test_session_scoped_secret_persistence(self, async_session: AsyncSession):
        """Test session-scoped secret database storage."""
        owner_id = uuid.uuid4()
        session_id = "chat-session-456"

        secret = Secret(
            owner_id=owner_id,
            name="session-api-key",
            type=SecretType.API_KEY.value,
            scope=SecretScope.SESSION.value,
            session_id=session_id,
            encrypted_value="encrypted_api_key",
        )

        async_session.add(secret)
        await async_session.commit()

        # Query by session_id
        result = await async_session.execute(select(Secret).where(Secret.session_id == session_id))
        retrieved = result.scalar_one()

        assert retrieved.scope == SecretScope.SESSION.value
        assert retrieved.session_id == session_id

    async def test_shared_secret_persistence(self, async_session: AsyncSession):
        """Test shared secret JSONB storage."""
        owner_id = uuid.uuid4()
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        secret = Secret(
            owner_id=owner_id,
            name="team-password",
            type=SecretType.PASSWORD.value,
            scope=SecretScope.SHARED.value,
            encrypted_value="encrypted_password",
            shared_with=[str(user_a), str(user_b)],
        )

        async_session.add(secret)
        await async_session.commit()
        await async_session.refresh(secret)

        # Verify JSONB persistence
        assert isinstance(secret.shared_with, list)
        assert str(user_a) in secret.shared_with
        assert str(user_b) in secret.shared_with


@pytest.fixture
async def async_session():
    """
    Provide async database session for tests.

    Note: In real implementation, this would use test database.
    For now, this is a placeholder to show test structure.
    """
    # TODO: Implement actual test database session
    # For Issue #870, this demonstrates the test pattern
    pytest.skip("Database session fixture not yet implemented")
