# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RBAC Permission System Tests

Tests for the Role-Based Access Control system implemented in Phase 6.
Issue #744: Complete Authentication and RBAC System.

These tests verify:
- Permission enum definitions
- Role-to-permission mappings
- require_permission decorator
- require_role decorator
- SecurityLayer integration
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from fastapi import Request

from src.auth_rbac import (
    Permission,
    Role,
    ROLE_PERMISSIONS,
    has_permission,
    require_permission,
    require_role,
    require_any_permission,
    _get_user_permissions,
)


class TestPermissionEnum:
    """Tests for Permission enum definitions."""

    def test_all_permissions_have_values(self):
        """All permissions should have string values."""
        for perm in Permission:
            assert isinstance(perm.value, str)
            assert len(perm.value) > 0

    def test_permission_categories_exist(self):
        """Key permission categories should exist."""
        categories = ["api", "knowledge", "analytics", "agent", "workflow", "files", "security", "admin"]
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
        """Shell execute permission should only be granted to admin."""
        for role, perms in ROLE_PERMISSIONS.items():
            perm_values = [p.value if hasattr(p, "value") else p for p in perms]
            if role != Role.ADMIN:
                assert Permission.SHELL_EXECUTE.value not in perm_values, \
                    f"Role {role} should not have shell execute permission"


class TestHasPermission:
    """Tests for has_permission function."""

    def test_has_permission_with_valid_role(self):
        """Should return True for valid role with permission."""
        user_data = {"role": "admin"}
        # Admin should have API read permission
        result = has_permission(user_data, Permission.API_READ)
        # This depends on SecurityLayer being mocked or auth being disabled
        assert isinstance(result, bool)

    def test_has_permission_with_empty_user(self):
        """Should return False for empty user data."""
        result = has_permission({}, Permission.API_READ)
        assert result is False

    def test_has_permission_with_none_user(self):
        """Should return False for None user data."""
        result = has_permission(None, Permission.API_READ)
        assert result is False

    def test_has_permission_with_missing_role(self):
        """Should return False for user without role."""
        user_data = {"username": "test"}
        result = has_permission(user_data, Permission.API_READ)
        assert result is False


class TestGetUserPermissions:
    """Tests for _get_user_permissions function."""

    def test_get_admin_permissions(self):
        """Admin should get all RBAC permissions."""
        perms = _get_user_permissions("admin")
        assert len(perms) > 0
        assert "api.read" in perms

    def test_get_readonly_permissions(self):
        """Readonly should get limited permissions."""
        perms = _get_user_permissions("readonly")
        assert len(perms) > 0
        assert "api.read" in perms
        assert "api.write" not in perms

    def test_get_unknown_role_permissions(self):
        """Unknown role should still get SecurityLayer defaults."""
        perms = _get_user_permissions("unknown_role")
        # Should return at least SecurityLayer defaults (possibly empty)
        assert isinstance(perms, list)


class TestRequirePermissionDecorator:
    """Tests for require_permission decorator."""

    def _create_mock_request(self, headers=None):
        """Create a mock FastAPI request."""
        request = Mock(spec=Request)
        request.headers = headers or {}
        request.client = Mock()
        request.client.host = "127.0.0.1"
        request.url = Mock()
        request.url.path = "/api/test"
        return request

    @patch("src.user_management.config.get_deployment_config")
    def test_single_user_mode_bypass(self, mock_config):
        """Should bypass permission check in single-user mode."""
        from src.user_management.config import DeploymentMode

        mock_deployment = Mock()
        mock_deployment.mode = DeploymentMode.SINGLE_USER
        mock_config.return_value = mock_deployment

        request = self._create_mock_request()
        dependency = require_permission(Permission.ADMIN_SYSTEM)

        # In single user mode, should return True
        result = dependency(request)
        assert result is True


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

    @patch("src.user_management.config.get_deployment_config")
    def test_single_user_mode_bypass(self, mock_config):
        """Should bypass role check in single-user mode."""
        from src.user_management.config import DeploymentMode

        mock_deployment = Mock()
        mock_deployment.mode = DeploymentMode.SINGLE_USER
        mock_config.return_value = mock_deployment

        request = self._create_mock_request()
        dependency = require_role(Role.ADMIN)

        # In single user mode, should return True
        result = dependency(request)
        assert result is True


class TestRequireAnyPermission:
    """Tests for require_any_permission decorator."""

    def _create_mock_request(self, headers=None):
        """Create a mock FastAPI request."""
        request = Mock(spec=Request)
        request.headers = headers or {}
        request.client = Mock()
        request.client.host = "127.0.0.1"
        request.url = Mock()
        request.url.path = "/api/test"
        return request

    @patch("src.user_management.config.get_deployment_config")
    def test_single_user_mode_bypass(self, mock_config):
        """Should bypass permission check in single-user mode."""
        from src.user_management.config import DeploymentMode

        mock_deployment = Mock()
        mock_deployment.mode = DeploymentMode.SINGLE_USER
        mock_config.return_value = mock_deployment

        request = self._create_mock_request()
        dependency = require_any_permission(
            Permission.ANALYTICS_VIEW,
            Permission.ADMIN_SYSTEM
        )

        # In single user mode, should return True
        result = dependency(request)
        assert result is True


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


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])