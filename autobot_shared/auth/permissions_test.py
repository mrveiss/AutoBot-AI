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


def test_superadmin_holds_no_permission():
    """The inversion #13854 made deliberately, asserted as the whole set.

    This test previously asserted the exact opposite — superadmin held every
    permission — and it passed for a reason that was never a decision:
    `role_has_permission` short-circuited on `is_admin_role`, so `ADMIN_ROLES`
    was silently the most permissive permission source in the system. Meanwhile
    `SecurityLayer.check_permission` denied superadmin those same permissions.
    Two canonical resolvers, opposite answers, for the most privileged role.

    Superadmin is now a `Role` member with an explicitly empty
    `ROLE_PERMISSIONS` entry, and every resolver reads that one mapping. It is
    administrative as a predicate (see `is_admin_role`) and holds no granular
    grant.
    """
    for perm in Permission:
        assert role_has_permission("superadmin", perm.value) is False, perm.value


def test_superadmin_is_still_administrative():
    """The predicate is unchanged — this is not a retirement of the role.

    The 17 `require_role("admin", "superadmin")` endpoints and every
    `is_admin_role` caller admit it exactly as before.
    """
    assert is_admin_role("superadmin") is True
    assert Role("superadmin") is Role.SUPERADMIN
    assert ROLE_PERMISSIONS[Role.SUPERADMIN] == []


def test_being_administrative_does_not_grant_permissions():
    """#13854 AC: `ADMIN_ROLES` must not be a permission source.

    Membership of ADMIN_ROLES and possession of a permission are now decided by
    different data. Asserted through a role that is in one and not the other, so
    a reintroduced short-circuit fails here rather than being invisible.
    """
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
