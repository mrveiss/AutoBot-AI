# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the SLM permission decision, including API-key authority (#16040 AC2, AC4, AC5, AC6).

``permission_allowed`` is the whole decision that ``require_permission`` and
``require_key_permission`` apply; ``services/auth.py`` only turns False into a
403. It is tested here directly, without FastAPI: no SLM test can import
``services/auth.py`` in isolation (see ``tests/api/test_require_permission.py``).
"""

from datetime import datetime, timedelta, timezone

import pytest

from autobot_shared.auth.permissions import Permission, Role
from services.api_key_authority import (
    key_scope_allows,
    legacy_grace_deadline,
    permission_allowed,
    resolve_role,
    role_for_user,
)

_CUTOFF = "2026-09-11"
_CUTOFF_DT = datetime(2026, 9, 11, tzinfo=timezone.utc)


class TestAScopedKeyInTheWholeDecision:
    """AC6: a narrow-scope key is refused a permission outside its scopes."""

    def test_a_narrow_scope_key_is_refused_an_out_of_scope_permission(self):
        key = {"sub": "a", "role": Role.ADMIN.value, "scopes": ["knowledge:read"], "api_key_id": "k"}
        assert permission_allowed(key, Permission.KNOWLEDGE_READ) is True
        assert permission_allowed(key, Permission.KNOWLEDGE_WRITE) is False
        assert permission_allowed(key, Permission.ADMIN_SYSTEM) is False

    def test_a_key_never_exceeds_its_owners_role(self):
        """AC2: the scope carries the permission, but the owner's role does not."""
        key = {"sub": "u", "role": Role.USER.value, "scopes": ["knowledge:write"], "api_key_id": "k"}
        assert permission_allowed(key, Permission.KNOWLEDGE_WRITE) is False

    def test_an_admin_scope_on_a_non_admin_owners_key_grants_no_admin_permission(self):
        key = {"sub": "u", "role": Role.USER.value, "scopes": ["admin:*"], "api_key_id": "k"}
        assert permission_allowed(key, Permission.ADMIN_SYSTEM) is False
        assert permission_allowed(key, Permission.API_READ) is True

    def test_a_session_caller_is_decided_by_role_alone(self):
        """The contrast case: without ``api_key_id`` there are no scopes to narrow it."""
        session = {"sub": "a", "role": Role.ADMIN.value}
        assert permission_allowed(session, Permission.KNOWLEDGE_WRITE) is True

    def test_a_key_in_its_grace_period_acts_with_its_owners_full_role(self):
        """AC5. It still never exceeds its owner."""
        key = {"sub": "u", "role": Role.USER.value, "scopes": [], "api_key_id": "k", "legacy_full_scope": True}
        assert permission_allowed(key, Permission.API_READ) is True
        assert permission_allowed(key, Permission.ADMIN_SYSTEM) is False


class TestTheKeyHalf:
    def test_a_wildcard_key_carries_its_whole_resource_and_nothing_else(self):
        key = {"scopes": ["files:*"], "api_key_id": "k"}
        assert key_scope_allows(key, Permission.FILES_DELETE) is True
        assert key_scope_allows(key, Permission.CHAT_USE) is False

    @pytest.mark.parametrize("scopes", ["admin:*", None, {"admin:*": True}])
    def test_a_malformed_scopes_value_carries_nothing(self, scopes):
        assert key_scope_allows({"scopes": scopes, "api_key_id": "k"}, Permission.API_READ) is False

    def test_only_a_literal_true_marks_a_legacy_key(self):
        """A truthy string must not buy full authority."""
        key = {"scopes": [], "api_key_id": "k", "legacy_full_scope": "yes"}
        assert key_scope_allows(key, Permission.ADMIN_SYSTEM) is False


class TestRoleResolution:
    def test_the_owner_role_follows_the_session_rule(self):
        assert role_for_user(True) is Role.ADMIN
        assert role_for_user(False) is Role.USER

    @pytest.mark.parametrize(
        ("caller", "expected"),
        [
            ({"role": "admin"}, Role.ADMIN),
            ({"role": "readonly"}, Role.READONLY),
            ({"role": "not-a-role"}, Role.USER),
            ({"admin": True}, Role.ADMIN),
            ({"admin": False}, Role.USER),
            ({}, Role.USER),
        ],
    )
    def test_the_role_claim_wins_and_the_legacy_flag_is_the_fallback(self, caller, expected):
        assert resolve_role(caller) is expected


class TestTheLegacyGracePeriod:
    """AC5: keys created before enforcement keep their owner's authority for the grace period only."""

    def test_a_key_created_before_the_cutoff_gets_the_grace_deadline(self):
        created = _CUTOFF_DT - timedelta(days=30)
        assert legacy_grace_deadline(created, enforced_from=_CUTOFF, grace_days=90) == _CUTOFF_DT + timedelta(days=90)

    def test_a_key_created_at_or_after_the_cutoff_is_subject_to_its_scopes(self):
        assert legacy_grace_deadline(_CUTOFF_DT, enforced_from=_CUTOFF, grace_days=90) is None
        assert legacy_grace_deadline(_CUTOFF_DT + timedelta(days=1), enforced_from=_CUTOFF, grace_days=90) is None

    def test_a_naive_timestamp_is_read_as_utc(self):
        assert legacy_grace_deadline(datetime(2026, 9, 10, 23, 0), enforced_from=_CUTOFF, grace_days=90) is not None

    def test_a_key_of_unknown_age_is_subject_to_its_scopes(self):
        """Fails closed: an unknown age must not buy full authority."""
        assert legacy_grace_deadline(None, enforced_from=_CUTOFF, grace_days=90) is None

    def test_the_grace_period_is_the_setting_not_a_constant(self):
        created = _CUTOFF_DT - timedelta(days=1)
        assert legacy_grace_deadline(created, enforced_from=_CUTOFF, grace_days=30) == _CUTOFF_DT + timedelta(days=30)
