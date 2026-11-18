# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
RBAC Permission System Tests

Tests for the Role-Based Access Control system implemented in Phase 6.
Issue #744: Complete Authentication and RBAC System.

These tests verify:
- Permission enum definitions
- Role-to-permission mappings
- require_permission / require_any_permission: the shared gate (#18263)
- require_role decorator
- SecurityLayer integration
"""

from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException, Request

from auth_rbac import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    _request_caller,
    require_any_permission,
    require_permission,
    require_role,
)
from testkit.canonical_gate import canonical_resolver


class TestPermissionEnum:
    """Tests for Permission enum definitions."""

    def test_all_permissions_have_values(self):
        """All permissions should have string values."""
        for perm in Permission:
            assert isinstance(perm.value, str)
            assert len(perm.value) > 0

    def test_permission_categories_exist(self):
        """Key permission categories should exist."""
        categories = [
            "api",
            "knowledge",
            "analytics",
            "agent",
            "workflow",
            "files",
            "security",
            "admin",
        ]
        for category in categories:
            matching = [p for p in Permission if p.value.startswith(category)]
            assert len(matching) > 0, f"No permissions found for category: {category}"

    def test_permission_naming_convention(self):
        """Permissions should follow naming convention: category.action or legacy format."""
        # Legacy permissions like 'allow_shell_execute' are allowed for backward compatibility
        legacy_permissions = {"allow_shell_execute"}
        for perm in Permission:
            if perm.value in legacy_permissions:
                continue  # Skip legacy permissions
            parts = perm.value.split(".")
            assert len(parts) >= 2, f"Permission {perm.value} doesn't follow naming convention"


class TestRoleEnum:
    """Tests for Role enum definitions."""

    def test_standard_roles_exist(self):
        """Standard roles should be defined."""
        expected_roles = ["admin", "operator", "analyst", "editor", "user", "readonly"]
        for role in expected_roles:
            assert Role(role), f"Role {role} not found"

    def test_role_values_are_lowercase(self):
        """Role values should be lowercase."""
        for role in Role:
            assert role.value == role.value.lower()


class TestRolePermissionMappings:
    """Tests for role-to-permission mappings."""

    def test_admin_has_all_permissions(self):
        """Admin role should have all permissions."""
        admin_perms = ROLE_PERMISSIONS.get(Role.ADMIN, [])
        # Admin should have the most permissions
        assert len(admin_perms) > 30, "Admin should have many permissions"

    def test_readonly_has_minimal_permissions(self):
        """Readonly role should have minimal permissions."""
        readonly_perms = ROLE_PERMISSIONS.get(Role.READONLY, [])
        # Readonly should only have view permissions
        for perm in readonly_perms:
            perm_val = perm.value if hasattr(perm, "value") else perm
            assert "write" not in perm_val.lower()
            assert "delete" not in perm_val.lower()
            assert "manage" not in perm_val.lower()
            assert "execute" not in perm_val.lower()

    def test_role_hierarchy(self):
        """Higher roles should have more permissions than lower roles."""
        admin_perms = len(ROLE_PERMISSIONS.get(Role.ADMIN, []))
        operator_perms = len(ROLE_PERMISSIONS.get(Role.OPERATOR, []))
        user_perms = len(ROLE_PERMISSIONS.get(Role.USER, []))
        readonly_perms = len(ROLE_PERMISSIONS.get(Role.READONLY, []))

        assert admin_perms > operator_perms
        assert operator_perms > user_perms
        assert user_perms > readonly_perms

    def test_shell_execute_only_admin(self):
        """Shell execute permission should only be granted to admin (and superadmin, derived from admin, #19125)."""
        for role, perms in ROLE_PERMISSIONS.items():
            perm_values = [p.value if hasattr(p, "value") else p for p in perms]
            if role not in (Role.ADMIN, Role.SUPERADMIN):
                assert (
                    Permission.SHELL_EXECUTE.value not in perm_values
                ), f"Role {role} should not have shell execute permission"


class TestRequirePermissionIsTheSharedGate:
    """#18263: the backend's require_permission is the shared gate's, bound to this service's caller."""

    def _request(self):
        request = Mock(spec=Request)
        request.headers = {}
        request.client = None
        request.url = Mock()
        request.url.path = "/api/test"
        return request

    async def test_the_caller_is_the_auth_middlewares_user(self):
        middleware = Mock(get_user_from_request=Mock(return_value={"role": "admin"}))
        with canonical_resolver("auth_rbac.resolve_human_user", middleware):
            assert await _request_caller(self._request()) == {"role": "admin"}

    async def test_unauthenticated_is_401(self):
        with pytest.raises(HTTPException) as exc:
            await require_permission(Permission.ADMIN_SYSTEM)(request=self._request(), caller=None)
        assert exc.value.status_code == 401

    async def test_denied_is_audited_then_403(self):
        with (
            patch("autobot_shared.auth.permission_gate.audit_permission_denied") as audit,
            patch("auth_rbac._permission_gate._wire_rbac", lambda: None),
        ):
            with pytest.raises(HTTPException) as exc:
                await require_any_permission(Permission.API_WRITE, Permission.ADMIN_SYSTEM)(
                    request=self._request(), caller={"role": "readonly", "username": "r"}
                )
        assert exc.value.status_code == 403
        audit.assert_awaited_once()

    async def test_allowed_returns_the_caller(self):
        caller = {"role": "admin"}
        assert await require_permission(Permission.ADMIN_SYSTEM)(request=self._request(), caller=caller) is caller

    def test_contrast_a_string_permission_fails_at_build_time(self):
        with pytest.raises(TypeError):
            require_permission("admin.system")


class TestRequireRoleDecorator:
    """Tests for require_role decorator."""

    def _create_mock_request(self, headers=None):
        """Create a mock FastAPI request."""
        request = Mock(spec=Request)
        request.headers = headers or {}
        request.client = Mock()
        request.client.host = "127.0.0.1"
        request.url = Mock()
        request.url.path = "/api/test"
        return request

    async def test_unauthenticated_request_denied(self):
        """No authenticated user → the decorator raises 401 (full auth always required)."""
        middleware = Mock(get_user_from_request=Mock(return_value=None))
        dependency = require_role(Role.ADMIN)
        with canonical_resolver("auth_rbac.resolve_human_user", middleware):
            with pytest.raises(HTTPException) as exc:
                await dependency(self._create_mock_request())
        assert exc.value.status_code == 401


class TestPermissionIntegration:
    """Integration tests for permission system."""

    def test_permission_string_conversion(self):
        """Permission enum should convert to string properly."""
        perm = Permission.ANALYTICS_VIEW
        assert str(perm.value) == "analytics.view"

    def test_permission_comparison(self):
        """Permissions should be comparable."""
        perm1 = Permission.ANALYTICS_VIEW
        perm2 = Permission.ANALYTICS_VIEW
        perm3 = Permission.ANALYTICS_EXPORT

        assert perm1 == perm2
        assert perm1 != perm3

    def test_role_comparison(self):
        """Roles should be comparable."""
        role1 = Role.ADMIN
        role2 = Role.ADMIN
        role3 = Role.USER

        assert role1 == role2
        assert role1 != role3


class TestIsAdminRole:
    """#12717: the single answer to "is this role administrative?".

    "superadmin" is passed as a raw string to require_role() at 17 call sites.
    It was not a member of the canonical Role enum, so hand-rolled
    ``role == "admin"`` checks silently locked superadmins out of read paths
    whose write paths already allowed them. #13854 made it a first-class Role
    member; ``is_admin_role`` remains the answer for imperative checks, and this
    class pins that it still admits both administrative roles.
    """

    def test_accepts_both_administrative_roles(self):
        from autobot_shared.auth.permissions import is_admin_role

        assert is_admin_role("admin") is True
        assert is_admin_role("superadmin") is True

    def test_rejects_every_non_administrative_role(self):
        from autobot_shared.auth.permissions import is_admin_role

        for role in ("user", "readonly", "operator", "analyst", "editor"):
            assert is_admin_role(role) is False, role

    def test_handles_missing_role_without_raising(self):
        from autobot_shared.auth.permissions import is_admin_role

        assert is_admin_role(None) is False
        assert is_admin_role("") is False

    def test_is_case_insensitive_to_match_require_role(self):
        """require_role lowercases both the user role and the allowed set, so a
        mixed-case token must not pass one gate and fail the other."""
        from autobot_shared.auth.permissions import is_admin_role

        assert is_admin_role("SuperAdmin") is True
        assert is_admin_role("ADMIN") is True

    def test_admin_roles_superset_of_the_canonical_enum_admin(self):
        from auth_rbac import ADMIN_ROLES

        assert Role.ADMIN.value in ADMIN_ROLES
        assert "superadmin" in ADMIN_ROLES


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
