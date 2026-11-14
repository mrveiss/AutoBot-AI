# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for require_permission logic — MVA-126.

Tests the three required denial scenarios plus role resolution through the
shared evaluator (``autobot_shared.auth.permission_evaluator``, #18263) that
``services.auth.require_permission`` applies. Role resolution is strict: the
``role`` claim must be exactly a ``Role`` value, with no legacy ``admin``-flag
fallback and no unknown-role-means-user.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "autobot_shared"))

from autobot_shared.auth.permission_evaluator import permission_allowed
from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role

# The decision under test is the shared evaluator itself (#18263), not a replica
# of it: a replica is how the old lenient role fallback outlived its decision.


def _has_permission(user_payload: dict, permission: Permission) -> bool:
    return permission_allowed(user_payload, permission)


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
# Strict role resolution (#18263): what the SLM used to resolve leniently
# ---------------------------------------------------------------------------


class TestStrictRoleResolution:
    def test_a_token_without_a_role_claim_is_denied_whatever_its_admin_flag(self):
        assert not _has_permission(LEGACY_ADMIN, Permission.ADMIN_SYSTEM)
        assert not _has_permission(LEGACY_USER, Permission.CHAT_USE)

    def test_an_unknown_role_is_denied_not_treated_as_user(self):
        bad = {"sub": "attacker", "admin": False, "role": "superadmin_inject"}
        assert not _has_permission(bad, Permission.ADMIN_SYSTEM)
        assert not _has_permission(bad, Permission.CHAT_USE)

    def test_an_empty_role_is_denied_whatever_its_admin_flag(self):
        assert not _has_permission({"sub": "x", "admin": True, "role": ""}, Permission.ADMIN_SYSTEM)

    def test_the_role_claim_is_case_sensitive(self):
        assert not _has_permission({"sub": "x", "role": "Admin"}, Permission.CHAT_USE)

    def test_the_control_an_exact_role_is_granted(self):
        assert _has_permission({"sub": "x", "role": "user"}, Permission.CHAT_USE)


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

    def test_services_auth_does_not_define_its_own_require_permission(self):
        """#18263: services/auth.py re-exports the shared gate's factories; a local def is a fork."""
        auth_src = (Path(__file__).parent.parent.parent / "services" / "auth.py").read_text(encoding="utf-8")
        assert "def require_permission" not in auth_src
        assert "require_permission = _permission_gate.require_permission" in auth_src

    def test_services_auth_imports_shared_permission(self):
        """Verify services/auth.py imports Permission from autobot_shared."""
        import re

        auth_src = (Path(__file__).parent.parent.parent / "services" / "auth.py").read_text()
        # Robust to co-imports on the same line (the exact-literal grep rotted
        # when the import gained ROLE_PERMISSIONS / Role, #11798).
        assert re.search(r"from autobot_shared\.auth\.permissions import .*\bPermission\b", auth_src)

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
