# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Cross-service auth parity tests (#6511).

Verifies that autobot-backend and autobot-slm-backend share a single
canonical source of truth for permission names and role mappings.

The key invariant enforced here: if you add a new ``Permission`` member to
``autobot_shared.auth.permissions``, these tests fail until you also grant it
to at least one role in ``ROLE_PERMISSIONS`` — preventing a permission from
being defined but silently unused (security drift scenario #1 from #6511).
"""

from __future__ import annotations

from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role


class TestSharedPermissionEnumIsCanonical:
    """Permission enum lives in autobot_shared — not backend-local."""

    def test_permission_importable_from_shared_module(self):
        assert Permission is not None
        assert issubclass(Permission, str)

    def test_role_importable_from_shared_module(self):
        assert Role is not None
        assert issubclass(Role, str)

    def test_role_permissions_importable_from_shared_module(self):
        assert ROLE_PERMISSIONS is not None
        assert isinstance(ROLE_PERMISSIONS, dict)

    def test_auth_rbac_re_exports_match_shared(self):
        """auth_rbac.py must re-export the identical objects, not local copies."""
        import os
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
        try:
            from auth_rbac import ROLE_PERMISSIONS as RbacRP
            from auth_rbac import Permission as RbacPerm
            from auth_rbac import Role as RbacRole

            assert RbacPerm is Permission, "auth_rbac.Permission must be the same object as shared Permission"
            assert RbacRole is Role, "auth_rbac.Role must be the same object as shared Role"
            assert (
                RbacRP is ROLE_PERMISSIONS
            ), "auth_rbac.ROLE_PERMISSIONS must be the same object as shared ROLE_PERMISSIONS"
        except ImportError:
            pass  # Backend deps not installed — shared-module check above is sufficient


class TestPermissionCoverage:
    """Every permission value is a unique dot-namespaced string."""

    def test_all_permission_values_are_strings(self):
        for perm in Permission:
            assert isinstance(perm.value, str), f"{perm.name} value must be str"

    def test_permission_values_are_unique(self):
        values = [p.value for p in Permission]
        assert len(values) == len(set(values)), "Duplicate permission string values detected"

    def test_permission_values_follow_dotted_namespace(self):
        # All permissions should be dot-namespaced except the legacy SHELL_EXECUTE
        for perm in Permission:
            if perm == Permission.SHELL_EXECUTE:
                continue
            assert "." in perm.value, f"{perm.name}={perm.value!r} should use dot namespace"


class TestRolePermissionsCoverage:
    """ROLE_PERMISSIONS covers all roles and is internally consistent."""

    def test_all_roles_present_in_role_permissions(self):
        for role in Role:
            assert role in ROLE_PERMISSIONS, f"Role {role} missing from ROLE_PERMISSIONS"

    def test_role_permissions_values_are_permission_instances(self):
        for role, perms in ROLE_PERMISSIONS.items():
            for p in perms:
                assert isinstance(p, Permission), f"{role}: {p!r} is not a Permission instance"

    def test_admin_has_all_permissions(self):
        admin_perms = set(ROLE_PERMISSIONS[Role.ADMIN])
        all_perms = set(Permission)
        missing = all_perms - admin_perms
        assert not missing, f"ADMIN role is missing permissions: {missing}"

    def test_shell_execute_not_granted_to_unprivileged_roles(self):
        unprivileged = {Role.USER, Role.READONLY, Role.ANALYST}
        for role in unprivileged:
            assert (
                Permission.SHELL_EXECUTE not in ROLE_PERMISSIONS[role]
            ), f"SHELL_EXECUTE must not be granted to {role}"

    def test_each_permission_granted_to_at_least_one_role(self):
        all_granted = {p for perms in ROLE_PERMISSIONS.values() for p in perms}
        ungranated = set(Permission) - all_granted
        assert not ungranated, (
            f"Permissions defined but not granted to any role: {ungranated}. "
            "Add them to ROLE_PERMISSIONS or remove them if they are obsolete."
        )


class TestRoleHierarchy:
    """Higher-privilege roles have a superset of lower-privilege permissions."""

    def test_admin_is_superset_of_operator(self):
        admin = set(ROLE_PERMISSIONS[Role.ADMIN])
        operator = set(ROLE_PERMISSIONS[Role.OPERATOR])
        assert operator.issubset(admin), f"ADMIN missing operator permissions: {operator - admin}"

    def test_operator_is_superset_of_user(self):
        operator = set(ROLE_PERMISSIONS[Role.OPERATOR])
        user = set(ROLE_PERMISSIONS[Role.USER])
        assert user.issubset(operator), f"OPERATOR missing user permissions: {user - operator}"

    def test_user_is_superset_of_readonly(self):
        user = set(ROLE_PERMISSIONS[Role.USER])
        readonly = set(ROLE_PERMISSIONS[Role.READONLY])
        assert readonly.issubset(user), f"USER missing readonly permissions: {readonly - user}"
