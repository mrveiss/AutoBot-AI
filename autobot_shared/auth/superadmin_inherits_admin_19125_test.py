# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Superadmin is the highest form of admin (#19125, owner decision 2026-10-21).

``Role.SUPERADMIN`` holds a superset of ``Role.ADMIN``'s permissions, derived
from admin's set. These tests iterate EVERY ``Permission`` so they cannot drift:
reverting the entry to ``[]`` (#13854's ruling) fails each of them.
"""

import asyncio
from types import SimpleNamespace

import pytest

from autobot_shared.auth.permission_evaluator import permission_allowed
from autobot_shared.auth.permission_gate import PermissionGate
from autobot_shared.auth.permissions import (
    ROLE_PERMISSIONS,
    SYSTEM_ROLES,
    Permission,
    Role,
    role_has_permission,
)

_SUPERADMIN = {"sub": "root", "role": Role.SUPERADMIN.value}
_REPRESENTATIVE = [
    Permission.MCP_DESKTOP_CONTROL,
    Permission.ADMIN_SYSTEM,
    Permission.SECURITY_MANAGE,
    Permission.ADMIN_USERS_WRITE,
    Permission.SHELL_EXECUTE,
    Permission.CHAT_USE,
]


def test_the_permission_enum_is_not_empty():
    assert len(list(Permission)) > 0, "vacuous guard"


@pytest.mark.parametrize("permission", list(Permission), ids=lambda p: p.value)
def test_every_admin_permission_is_held_by_superadmin(permission):
    """For every P: role_has_permission(ADMIN, P) implies role_has_permission(SUPERADMIN, P)."""
    if role_has_permission(Role.ADMIN, permission.value):
        assert role_has_permission(Role.SUPERADMIN, permission.value) is True
        assert permission_allowed(_SUPERADMIN, permission) is True


def test_superadmin_grants_are_a_superset_derived_from_admin():
    assert set(ROLE_PERMISSIONS[Role.ADMIN]) <= set(ROLE_PERMISSIONS[Role.SUPERADMIN])
    assert ROLE_PERMISSIONS[Role.SUPERADMIN] is not ROLE_PERMISSIONS[Role.ADMIN]
    assert len(ROLE_PERMISSIONS[Role.SUPERADMIN]) == len(set(ROLE_PERMISSIONS[Role.SUPERADMIN]))


def test_the_db_seed_rows_agree_with_the_canonical_mapping():
    """One canonical path: the DB seed is generated from ROLE_PERMISSIONS."""
    seeded = set(SYSTEM_ROLES["superadmin"]["permissions"])
    assert {p.value for p in ROLE_PERMISSIONS[Role.SUPERADMIN]} <= seeded
    assert set(SYSTEM_ROLES["admin"]["permissions"]) <= seeded


@pytest.mark.parametrize("permission", _REPRESENTATIVE, ids=lambda p: p.value)
def test_require_permission_routes_admit_superadmin_wherever_they_admit_admin(permission):
    """The shared ``require_permission`` gate -- the one every route uses."""
    gate = PermissionGate(lambda: None)
    request = SimpleNamespace()
    admin = {"sub": "a", "role": Role.ADMIN.value}

    assert asyncio.run(gate.enforce(request, admin, (permission,))) is admin
    assert asyncio.run(gate.enforce(request, _SUPERADMIN, (permission,))) is _SUPERADMIN
