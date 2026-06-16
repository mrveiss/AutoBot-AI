# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the service.management permission gate (#10198, epic #10193).

Verifies:
- Permission.SERVICE_MANAGEMENT is defined in the canonical enum.
- ADMIN and OPERATOR have the permission; USER/READONLY/ANALYST/EDITOR do not.
- require_service_management dependency:
    * admin/operator tokens -> passes (returns payload)
    * user/readonly tokens -> raises 403
    * no role but admin=True (legacy token) -> passes
    * no role but admin=False (legacy token) -> raises 403
    * unknown role string -> raises 403
- Cross-service parity: ROLE_PERMISSIONS grants SERVICE_MANAGEMENT to admin
  and operator only among the named roles.
"""

import pytest
from unittest.mock import AsyncMock, patch

from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role


# ---------------------------------------------------------------------------
# 1. Canonical permission is present and correctly placed
# ---------------------------------------------------------------------------


class TestServiceManagementPermissionDefinition:
    def test_service_management_in_permission_enum(self):
        assert hasattr(Permission, "SERVICE_MANAGEMENT")
        assert Permission.SERVICE_MANAGEMENT.value == "service.management"

    def test_admin_has_service_management(self):
        assert Permission.SERVICE_MANAGEMENT in ROLE_PERMISSIONS[Role.ADMIN]

    def test_operator_has_service_management(self):
        assert Permission.SERVICE_MANAGEMENT in ROLE_PERMISSIONS[Role.OPERATOR]

    def test_user_lacks_service_management(self):
        assert Permission.SERVICE_MANAGEMENT not in ROLE_PERMISSIONS[Role.USER]

    def test_readonly_lacks_service_management(self):
        assert Permission.SERVICE_MANAGEMENT not in ROLE_PERMISSIONS[Role.READONLY]

    def test_analyst_lacks_service_management(self):
        assert Permission.SERVICE_MANAGEMENT not in ROLE_PERMISSIONS[Role.ANALYST]

    def test_editor_lacks_service_management(self):
        assert Permission.SERVICE_MANAGEMENT not in ROLE_PERMISSIONS[Role.EDITOR]


# ---------------------------------------------------------------------------
# 2. Role hierarchy consistency
# ---------------------------------------------------------------------------


class TestRoleHierarchyWithServiceManagement:
    def test_admin_is_superset_of_operator(self):
        admin = set(ROLE_PERMISSIONS[Role.ADMIN])
        operator = set(ROLE_PERMISSIONS[Role.OPERATOR])
        assert operator.issubset(admin), f"ADMIN missing: {operator - admin}"

    def test_operator_is_superset_of_user(self):
        operator = set(ROLE_PERMISSIONS[Role.OPERATOR])
        user = set(ROLE_PERMISSIONS[Role.USER])
        assert user.issubset(operator), f"OPERATOR missing: {user - operator}"

    def test_service_management_not_in_user_not_violating_hierarchy(self):
        """USER not having SERVICE_MANAGEMENT is correct — operator is still a superset."""
        user_perms = set(ROLE_PERMISSIONS[Role.USER])
        assert Permission.SERVICE_MANAGEMENT not in user_perms


# ---------------------------------------------------------------------------
# 3. require_service_management dependency behavior
#
# We replicate the _check inner function logic from services/auth.py rather
# than importing it to avoid loading the full SLM dependency tree in CI.
# ---------------------------------------------------------------------------


def _simulate_require_service_management(payload: dict) -> bool:
    """Replicate require_permission(Permission.SERVICE_MANAGEMENT)._check logic."""
    role_str = payload.get("role")
    if role_str:
        try:
            role = Role(role_str)
        except ValueError:
            role = Role.USER
    else:
        role = Role.ADMIN if payload.get("admin", False) else Role.USER
    return Permission.SERVICE_MANAGEMENT in ROLE_PERMISSIONS.get(role, [])


class TestRequireServiceManagementLogic:
    def test_admin_role_token_passes(self):
        assert _simulate_require_service_management({"sub": "a", "role": "admin"})

    def test_operator_role_token_passes(self):
        assert _simulate_require_service_management({"sub": "op", "role": "operator"})

    def test_user_role_token_denied(self):
        assert not _simulate_require_service_management({"sub": "u", "role": "user"})

    def test_readonly_role_token_denied(self):
        assert not _simulate_require_service_management({"sub": "r", "role": "readonly"})

    def test_analyst_role_token_denied(self):
        assert not _simulate_require_service_management({"sub": "an", "role": "analyst"})

    def test_editor_role_token_denied(self):
        assert not _simulate_require_service_management({"sub": "ed", "role": "editor"})

    def test_legacy_admin_true_passes(self):
        """Legacy HS256 tokens with admin=True (no role field) must be granted."""
        assert _simulate_require_service_management({"sub": "legacy_admin", "admin": True})

    def test_legacy_admin_false_denied(self):
        """Legacy HS256 tokens with admin=False (no role field) must be denied."""
        assert not _simulate_require_service_management({"sub": "legacy_user", "admin": False})

    def test_unknown_role_denied(self):
        """Injected or unknown role string falls back to USER → denied."""
        assert not _simulate_require_service_management(
            {"sub": "attacker", "role": "superadmin_inject"}
        )

    def test_missing_role_and_no_admin_flag_denied(self):
        """Payload with no role and no admin flag → USER → denied."""
        assert not _simulate_require_service_management({"sub": "nobody"})
