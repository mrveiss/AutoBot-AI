# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The canonical role vocabulary has no members outside it (#13854, #12786).

``superadmin`` was administrative — ``ADMIN_ROLES`` held it, ``is_admin_role``
returned True for it, 17 ``require_role`` guards admitted it — while not being a
``Role`` member and holding no ``ROLE_PERMISSIONS`` entry. It therefore resolved
four different ways at once: allow-all through ``role_has_permission``, deny-all
through ``SecurityLayer.check_permission``, admitted by ``require_role``, and
``ValueError`` through ``Role()``.

These tests pin the properties that made that state possible, so it cannot
reassemble itself:

1. every administrative role is a real ``Role`` with a real grant list;
2. being administrative is not, by itself, a grant;
3. every ``Role`` member has an entry, so no lookup falls off the mapping.

Each test asserts the PRESENCE of what it expects, never merely the absence of a
failure — an empty vocabulary would otherwise satisfy every "nothing is wrong"
assertion here.
"""

import pytest

from autobot_shared.auth.permissions import (
    ADMIN_ROLES,
    ROLE_PERMISSIONS,
    _ROLE_META,
    Permission,
    Role,
    is_admin_role,
    role_has_permission,
)

# The vocabulary as of #13854, written out. A rename or a removal fails here
# first, with a message naming the member — rather than silently shrinking the
# sets every other test in this file derives from the enum.
EXPECTED_ROLE_VALUES = {
    "admin",
    "superadmin",
    "operator",
    "analyst",
    "editor",
    "user",
    "readonly",
}
EXPECTED_ADMIN_ROLE_VALUES = {"admin", "superadmin"}


# --------------------------------------------------- the vocabulary is present


def test_the_role_enum_holds_exactly_the_expected_members():
    """Presence, not absence. Guards against both a dropped and an added role."""
    assert {role.value for role in Role} == EXPECTED_ROLE_VALUES


def test_superadmin_is_a_member():
    """Stated on its own because it is the member #13854 exists to add.

    A regression that removes it would still pass a test comparing two derived
    sets to each other.
    """
    assert Role.SUPERADMIN in Role
    assert Role("superadmin") is Role.SUPERADMIN
    assert Role.SUPERADMIN.value == "superadmin"


# ------------------------------------- AC: every ADMIN_ROLES member is canonical


def test_admin_roles_is_not_empty():
    """The guard below is vacuous over an empty set — check the subject exists."""
    assert ADMIN_ROLES == EXPECTED_ADMIN_ROLE_VALUES
    assert len(ADMIN_ROLES) == 2


@pytest.mark.parametrize("role_value", sorted(EXPECTED_ADMIN_ROLE_VALUES))
def test_every_administrative_role_is_a_role_member_with_a_grant_list(role_value):
    """#13854 AC: ``ADMIN_ROLES`` may not name a role the enum does not have.

    This is the assertion that would have failed before #13854 —
    ``Role("superadmin")`` raised — and it is parametrised over the literal
    expected set rather than over ``ADMIN_ROLES`` itself, so an ADMIN_ROLES that
    lost a member cannot make its own guard pass by shrinking.
    """
    role = Role(role_value)
    assert role in ROLE_PERMISSIONS, f"{role_value} is administrative but has no ROLE_PERMISSIONS entry"
    assert is_admin_role(role_value) is True


def test_admin_roles_cannot_name_a_non_role():
    """Derived from the enum, so a bare string cannot be added to it."""
    for value in ADMIN_ROLES:
        assert Role(value) in Role


# ------------------------------ AC: ADMIN_ROLES is not a permission source


def test_being_administrative_grants_nothing_by_itself():
    """The core #13854 AC, asserted through the role that separates the two.

    ``superadmin`` is in ``ADMIN_ROLES`` and holds an empty grant list. If any
    resolver ever again short-circuits on the administrative predicate, this
    fails. Asserted over the WHOLE Permission enum, not a sample, so a partial
    reintroduction cannot slip through.
    """
    assert is_admin_role("superadmin") is True
    assert ROLE_PERMISSIONS[Role.SUPERADMIN] == []

    granted = [p.value for p in Permission if role_has_permission("superadmin", p.value)]
    assert granted == [], f"ADMIN_ROLES membership leaked {len(granted)} permissions: {granted}"


def test_admin_holds_every_permission_from_its_own_entry():
    """The invariant that made removing the short-circuit safe (#13854).

    ``role_has_permission`` used to return True for anything ``is_admin_role``
    accepted. Removing that is only behaviour-preserving for ``admin`` because
    admin's own ROLE_PERMISSIONS entry already covers every Permission member.
    That was measured once; this asserts it continuously, because a future
    permission added to the enum but not granted to admin would silently make
    the removal a regression.
    """
    admin_grants = {p.value for p in ROLE_PERMISSIONS[Role.ADMIN]}
    every_permission = {p.value for p in Permission}

    assert every_permission, "Permission enum is empty — this guard would be vacuous"
    assert every_permission - admin_grants == set(), "admin no longer holds every Permission"

    for permission in Permission:
        assert role_has_permission("admin", permission.value) is True, permission.value


# ------------------------------------------- no member falls off the mapping


def test_every_role_has_a_role_permissions_entry():
    """A missing entry used to raise ``KeyError`` at request time.

    ``role_has_permission`` subscripted ``_ROLE_PERMISSION_VALUES`` directly, so
    a ``Role`` member added without a grant list crashed the permission check
    instead of denying it.
    """
    assert set(Role), "Role enum is empty — this guard would be vacuous"
    missing = {role.value for role in Role if role not in ROLE_PERMISSIONS}
    assert missing == set(), f"Role members with no ROLE_PERMISSIONS entry: {missing}"


def test_every_role_has_role_metadata():
    """A missing ``_ROLE_META`` entry silently seeds priority 0 — below readonly."""
    missing = {role.value for role in Role if role not in _ROLE_META}
    assert missing == set(), f"Role members with no _ROLE_META entry: {missing}"


@pytest.mark.parametrize("unknown", ["not-a-role", "", None, "platform_admin", "guest"])
def test_an_unresolvable_role_is_denied_rather_than_raising(unknown):
    """Fail closed, and fail quietly — never a 500 from the permission gate."""
    assert role_has_permission(unknown, Permission.API_READ.value) is False
