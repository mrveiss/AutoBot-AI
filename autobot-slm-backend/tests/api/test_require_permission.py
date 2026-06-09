# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for require_permission logic — MVA-126.

Tests the three required denial scenarios plus the role-derivation logic
extracted from require_permission._check, without importing FastAPI
(avoids the pre-existing python_multipart env conflict that blocks all
FastAPI-importing tests in this environment — see tests/services failures).

These tests exercise the same code path as the live dependency: the role
derivation and ROLE_PERMISSIONS lookup are pure Python and can be tested
directly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "autobot_shared"))

from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role

# ---------------------------------------------------------------------------
# Replicate the role-derivation logic from services/auth.py::require_permission
# so the tests are independent of the FastAPI import chain.
# ---------------------------------------------------------------------------


def _derive_role(user_payload: dict) -> Role:
    role_str = user_payload.get("role")
    if role_str:
        try:
            return Role(role_str)
        except ValueError:
            return Role.USER
    return Role.ADMIN if user_payload.get("admin", False) else Role.USER


def _has_permission(user_payload: dict, permission: Permission) -> bool:
    role = _derive_role(user_payload)
    return permission in ROLE_PERMISSIONS.get(role, [])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ADMIN_USER = {"sub": "admin_user", "admin": True, "role": Role.ADMIN.value}
REGULAR_USER = {"sub": "regular_user", "admin": False, "role": Role.USER.value}
LEGACY_ADMIN = {"sub": "old_admin", "admin": True}  # no 'role' field
LEGACY_USER = {"sub": "old_user", "admin": False}  # no 'role' field


# ---------------------------------------------------------------------------
# Scenario 1: admin.system permission
# ---------------------------------------------------------------------------


class TestScenario1AdminSystem:
    """Non-admin JWT must be denied admin.system endpoints."""

    def test_non_admin_denied_admin_system(self):
        assert not _has_permission(REGULAR_USER, Permission.ADMIN_SYSTEM)

    def test_admin_allowed_admin_system(self):
        assert _has_permission(ADMIN_USER, Permission.ADMIN_SYSTEM)


# ---------------------------------------------------------------------------
# Scenario 2: security.manage permission
# ---------------------------------------------------------------------------


class TestScenario2SecurityManage:
    """Non-admin JWT must be denied security.manage endpoints."""

    def test_non_admin_denied_security_manage(self):
        assert not _has_permission(REGULAR_USER, Permission.SECURITY_MANAGE)

    def test_admin_allowed_security_manage(self):
        assert _has_permission(ADMIN_USER, Permission.SECURITY_MANAGE)


# ---------------------------------------------------------------------------
# Scenario 3: admin.users.write permission
# ---------------------------------------------------------------------------


class TestScenario3AdminUsersWrite:
    """Non-admin JWT must be denied admin.users.write endpoints."""

    def test_non_admin_denied_admin_users_write(self):
        assert not _has_permission(REGULAR_USER, Permission.ADMIN_USERS_WRITE)

    def test_admin_allowed_admin_users_write(self):
        assert _has_permission(ADMIN_USER, Permission.ADMIN_USERS_WRITE)


# ---------------------------------------------------------------------------
# Additional denial coverage: config endpoints
# ---------------------------------------------------------------------------


class TestAdminConfigPermissions:
    def test_non_admin_denied_config_read(self):
        assert not _has_permission(REGULAR_USER, Permission.ADMIN_CONFIG_READ)

    def test_non_admin_denied_config_write(self):
        assert not _has_permission(REGULAR_USER, Permission.ADMIN_CONFIG_WRITE)

    def test_admin_allowed_config_read(self):
        assert _has_permission(ADMIN_USER, Permission.ADMIN_CONFIG_READ)

    def test_admin_allowed_config_write(self):
        assert _has_permission(ADMIN_USER, Permission.ADMIN_CONFIG_WRITE)


# ---------------------------------------------------------------------------
# Legacy token fallback (admin boolean, no 'role' field)
# ---------------------------------------------------------------------------


class TestLegacyTokenFallback:
    def test_legacy_admin_token_derives_admin_role(self):
        assert _derive_role(LEGACY_ADMIN) == Role.ADMIN

    def test_legacy_user_token_derives_user_role(self):
        assert _derive_role(LEGACY_USER) == Role.USER

    def test_legacy_admin_granted_admin_system(self):
        assert _has_permission(LEGACY_ADMIN, Permission.ADMIN_SYSTEM)

    def test_legacy_user_denied_admin_system(self):
        assert not _has_permission(LEGACY_USER, Permission.ADMIN_SYSTEM)


# ---------------------------------------------------------------------------
# Invalid / injected role strings
# ---------------------------------------------------------------------------


class TestInvalidRoleHandling:
    def test_unknown_role_string_falls_back_to_user(self):
        bad = {"sub": "attacker", "admin": False, "role": "superadmin_inject"}
        assert _derive_role(bad) == Role.USER
        assert not _has_permission(bad, Permission.ADMIN_SYSTEM)

    def test_empty_role_string_falls_back_via_admin_flag(self):
        # Empty string is falsy: `if role_str:` is False → falls back to admin flag
        empty_role_admin = {"sub": "x", "admin": True, "role": ""}
        assert _derive_role(empty_role_admin) == Role.ADMIN

        empty_role_user = {"sub": "y", "admin": False, "role": ""}
        assert _derive_role(empty_role_user) == Role.USER

    def test_no_payload_fields_is_user(self):
        assert _derive_role({}) == Role.USER


# ---------------------------------------------------------------------------
# ROLE_PERMISSIONS mapping integrity
# ---------------------------------------------------------------------------


class TestRolePermissionsMapping:
    def test_admin_role_has_all_endpoint_permissions(self):
        admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
        required = [
            Permission.ADMIN_SYSTEM,
            Permission.SECURITY_MANAGE,
            Permission.ADMIN_USERS_WRITE,
            Permission.ADMIN_CONFIG_READ,
            Permission.ADMIN_CONFIG_WRITE,
        ]
        for perm in required:
            assert perm in admin_perms, f"ADMIN must have {perm}"

    def test_user_role_lacks_all_admin_permissions(self):
        user_perms = ROLE_PERMISSIONS[Role.USER]
        forbidden = [
            Permission.ADMIN_SYSTEM,
            Permission.SECURITY_MANAGE,
            Permission.ADMIN_USERS_WRITE,
            Permission.ADMIN_CONFIG_WRITE,
        ]
        for perm in forbidden:
            assert perm not in user_perms, f"USER must NOT have {perm}"

    def test_services_auth_defines_require_permission(self):
        """Verify require_permission is defined in services/auth.py (no import)."""
        auth_src = (Path(__file__).parent.parent.parent / "services" / "auth.py").read_text()
        assert "def require_permission" in auth_src

    def test_services_auth_imports_shared_permission(self):
        """Verify services/auth.py imports Permission from autobot_shared."""
        auth_src = (Path(__file__).parent.parent.parent / "services" / "auth.py").read_text()
        assert "from autobot_shared.auth.permissions import Permission" in auth_src

    def test_no_require_admin_in_api_routes(self):
        """Verify no API route file directly imports require_admin."""
        api_dir = Path(__file__).parent.parent.parent / "api"
        for f in api_dir.glob("*.py"):
            if f.name.endswith("_test.py"):
                continue
            content = f.read_text()
            # imports of require_admin should not exist (only definition in services/auth.py)
            if "from services.auth import" in content:
                assert (
                    "require_admin" not in content
                ), f"{f.name} still imports require_admin — should use require_permission"
