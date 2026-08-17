# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for `role_has_permission` (#14420).

Added as a small reusable helper alongside `ROLE_PERMISSIONS` so a second
consumer (`middleware.builtin.permission_enforcement`, in autobot-backend)
does not need its own copy of the role/permission membership check
`services.mcp_dispatch._would_deny` already hand-rolls. Both backends import
this module (see the module docstring), so it is tested directly here rather
than only through one caller's delegate.
"""

import pytest

from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role, role_has_permission

# A permission every non-readonly role holds, and one only admin holds —
# picked from the real enum/mapping rather than invented values, so a
# ROLE_PERMISSIONS edit that removes a grant is caught here too.
_WIDELY_GRANTED_PERM = Permission.API_READ.value  # every role in ROLE_PERMISSIONS
_ADMIN_ONLY_PERM = Permission.ADMIN_SYSTEM.value  # Role.ADMIN only


@pytest.mark.parametrize("role", list(Role))
def test_every_role_holds_its_own_granted_permissions(role):
    """Ground truth: role_has_permission must agree with ROLE_PERMISSIONS
    itself for every role the enum defines, not just the ones exercised
    elsewhere."""
    for perm in ROLE_PERMISSIONS[role]:
        assert role_has_permission(role.value, perm.value) is True, f"{role.value} should hold {perm.value}"


def test_readonly_lacks_a_write_permission():
    assert role_has_permission(Role.READONLY.value, _ADMIN_ONLY_PERM) is False


def test_admin_holds_every_permission():
    for perm in Permission:
        assert role_has_permission("admin", perm.value) is True, perm.value


def test_superadmin_holds_every_permission():
    """`superadmin` is administrative but not a `Role` enum member (#12704/#12717) —
    `is_admin_role` is the canonical, case-insensitive answer."""
    for perm in Permission:
        assert role_has_permission("superadmin", perm.value) is True, perm.value


def test_admin_role_is_case_insensitive():
    assert role_has_permission("ADMIN", _ADMIN_ONLY_PERM) is True
    assert role_has_permission("Admin", _ADMIN_ONLY_PERM) is True


@pytest.mark.parametrize("bad_role", [None, "", "not-a-real-role", "guest"])
def test_unrecognised_or_absent_role_fails_closed(bad_role):
    """An absent or unrecognised role must never default to permissive —
    this is the same fail-closed posture #14420 relies on."""
    assert role_has_permission(bad_role, _WIDELY_GRANTED_PERM) is False
