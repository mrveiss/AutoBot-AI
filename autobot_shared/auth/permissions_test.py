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

from autobot_shared.auth.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    is_admin_role,
    role_has_permission,
)

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


def test_superadmin_holds_every_permission_admin_holds():
    """#19125 (owner decision 2026-10-21): "Super admin is the highest form of admin".

    Asserted over the WHOLE `Permission` enum so it cannot drift: for every
    permission P, admin holding P implies superadmin holding P. This reverses
    #13854's empty SUPERADMIN entry; the grants are derived from admin's set,
    so a permission later added to admin is inherited automatically.
    """
    assert list(Permission), "Permission enum is empty -- this guard would be vacuous"
    for perm in Permission:
        if role_has_permission("admin", perm.value):
            assert role_has_permission("superadmin", perm.value) is True, perm.value
    assert set(ROLE_PERMISSIONS[Role.ADMIN]) <= set(ROLE_PERMISSIONS[Role.SUPERADMIN])
    assert ROLE_PERMISSIONS[Role.SUPERADMIN] is not ROLE_PERMISSIONS[Role.ADMIN], "derived, not aliased"


def test_superadmin_holds_every_permission():
    for perm in Permission:
        assert role_has_permission("superadmin", perm.value) is True, perm.value


def test_superadmin_is_still_administrative():
    """The predicate is unchanged — this is not a retirement of the role.

    The 17 `require_role("admin", "superadmin")` endpoints and every
    `is_admin_role` caller admit it exactly as before.
    """
    assert is_admin_role("superadmin") is True
    assert Role("superadmin") is Role.SUPERADMIN


def test_being_administrative_does_not_grant_permissions(monkeypatch):
    """#13854 AC, kept by #19125: `ADMIN_ROLES` must not be a permission source.

    Superadmin now HOLDS permissions, but through its ROLE_PERMISSIONS entry,
    not through the predicate. Emptying that entry's resolved table must deny
    even though `is_admin_role` stays True -- a reintroduced short-circuit
    fails here.
    """
    from autobot_shared.auth import permissions as mod

    monkeypatch.setitem(mod._ROLE_PERMISSION_VALUES, Role.SUPERADMIN, frozenset())
    assert is_admin_role("superadmin") is True
    assert role_has_permission("superadmin", Permission.SHELL_EXECUTE.value) is False
    assert role_has_permission("superadmin", Permission.ADMIN_SYSTEM.value) is False


def test_admin_role_is_case_insensitive():
    assert role_has_permission("ADMIN", _ADMIN_ONLY_PERM) is True
    assert role_has_permission("Admin", _ADMIN_ONLY_PERM) is True


@pytest.mark.parametrize("bad_role", [None, "", "not-a-real-role", "guest"])
def test_unrecognised_or_absent_role_fails_closed(bad_role):
    """An absent or unrecognised role must never default to permissive —
    this is the same fail-closed posture #14420 relies on."""
    assert role_has_permission(bad_role, _WIDELY_GRANTED_PERM) is False
