# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM permission parity tests (GH #6511).

Placed in autobot_shared/auth/ so they run WITHOUT the autobot-slm-backend
conftest.py stubs (which MagicMock user_management.models and sqlalchemy).
Instead, the SLM role module is loaded directly from its file path.

Guarantees:
- SYSTEM_PERMISSIONS covers every value in the canonical Permission enum.
- SYSTEM_ROLES['admin'] covers every shared permission (except SHELL_EXECUTE).
- SYSTEM_ROLES references only names that exist in SYSTEM_PERMISSIONS.
- Each shared role's ROLE_PERMISSIONS is a subset of the matching SYSTEM_ROLES entry.
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role

_SLM_ROOT = Path(__file__).parent.parent.parent / "autobot-slm-backend"


def _load_slm_role_module():
    """Load user_management/models/role.py directly without executing any __init__.py."""
    role_path = _SLM_ROOT / "user_management" / "models" / "role.py"
    if not role_path.exists():
        return None

    # Build minimal stubs so role.py's ORM class declarations don't fail.
    # role.py does: class Permission(Base, TimestampMixin) — we need real
    # classes (not MagicMock) as bases to avoid metaclass conflicts.
    class _DummyBase:
        pass

    class _DummyMixin:
        pass

    _base_mod = types.ModuleType("user_management.models.base")
    _base_mod.Base = _DummyBase  # type: ignore[attr-defined]
    _base_mod.TimestampMixin = _DummyMixin  # type: ignore[attr-defined]
    _base_mod.TenantMixin = _DummyMixin  # type: ignore[attr-defined]

    # SQLAlchemy stubs — only needed for column decorators, not for constants.
    _sa_stub = MagicMock()
    _sa_orm_stub = MagicMock()
    _sa_pg_stub = MagicMock()

    stub_overrides: dict[str, object] = {
        "user_management.models.base": _base_mod,
        "sqlalchemy": _sa_stub,
        "sqlalchemy.orm": _sa_orm_stub,
        "sqlalchemy.ext": MagicMock(),
        "sqlalchemy.ext.asyncio": MagicMock(),
        "sqlalchemy.dialects": MagicMock(),
        "sqlalchemy.dialects.postgresql": _sa_pg_stub,
    }

    saved: dict[str, object] = {}
    for name, stub in stub_overrides.items():
        saved[name] = sys.modules.get(name, _SENTINEL)
        sys.modules[name] = stub  # type: ignore[assignment]

    spec = importlib.util.spec_from_file_location("_slm_role_isolated", role_path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    finally:
        for name, original in saved.items():
            if original is _SENTINEL:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original  # type: ignore[assignment]

    return mod


_SENTINEL = object()
_slm_role = _load_slm_role_module()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_perm_values() -> set[str]:
    return {p.value for p in Permission}


def _all_role_perm_values() -> set[str]:
    values: set[str] = set()
    for perms in ROLE_PERMISSIONS.values():
        for p in perms:
            values.add(p.value if isinstance(p, Permission) else p)
    return values


# ---------------------------------------------------------------------------
# Shared module internal consistency
# ---------------------------------------------------------------------------


def test_every_permission_assigned_to_at_least_one_role():
    """Every Permission enum value must appear in ROLE_PERMISSIONS for at least one role."""
    uncovered = _all_perm_values() - _all_role_perm_values()
    assert not uncovered, "Permissions defined in the enum but not assigned to any role:\n" + "\n".join(
        f"  {p}" for p in sorted(uncovered)
    )


def test_role_permissions_only_reference_known_values():
    """ROLE_PERMISSIONS must not contain strings absent from the Permission enum."""
    unknown = _all_role_perm_values() - _all_perm_values()
    assert not unknown, f"ROLE_PERMISSIONS references strings not in Permission enum: {unknown}"


def test_all_roles_have_role_permissions_entry():
    """Every Role enum value must have a ROLE_PERMISSIONS key."""
    missing = {r for r in Role if r not in ROLE_PERMISSIONS}
    assert not missing, f"Roles with no ROLE_PERMISSIONS entry: {missing}"


def test_admin_role_contains_all_permissions():
    """ROLE_PERMISSIONS[Role.ADMIN] must cover every Permission except SHELL_EXECUTE."""
    admin_values = {p.value if isinstance(p, Permission) else p for p in ROLE_PERMISSIONS[Role.ADMIN]}
    required = _all_perm_values() - {Permission.SHELL_EXECUTE.value}
    missing = required - admin_values
    assert not missing, "ROLE_PERMISSIONS[Role.ADMIN] is missing permissions:\n" + "\n".join(
        f"  {p}" for p in sorted(missing)
    )


# ---------------------------------------------------------------------------
# SLM backend parity
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def slm_role():
    if _slm_role is None:
        pytest.skip("autobot-slm-backend/user_management/models/role.py not found")
    return _slm_role


def test_slm_system_permissions_cover_shared_enum(slm_role):
    """Adding a Permission to autobot_shared must fail until SYSTEM_PERMISSIONS is updated."""
    slm_names = {row[0] for row in slm_role.SYSTEM_PERMISSIONS}
    missing = _all_perm_values() - slm_names
    assert not missing, (
        "Permissions in shared enum not seeded into SLM SYSTEM_PERMISSIONS:\n"
        + "\n".join(f"  {p}" for p in sorted(missing))
        + "\nAdd them to SYSTEM_PERMISSIONS in "
        "autobot-slm-backend/user_management/models/role.py."
    )


def test_slm_admin_role_covers_all_shared_permissions(slm_role):
    """SLM 'admin' role must grant every shared permission (SHELL_EXECUTE excepted)."""
    admin_perms = set(slm_role.SYSTEM_ROLES["admin"]["permissions"])
    required = _all_perm_values() - {Permission.SHELL_EXECUTE.value}
    missing = required - admin_perms
    assert not missing, "SLM SYSTEM_ROLES['admin'] missing shared permissions:\n" + "\n".join(
        f"  {p}" for p in sorted(missing)
    )


def test_slm_system_roles_reference_only_known_permissions(slm_role):
    """SYSTEM_ROLES must not reference names absent from SYSTEM_PERMISSIONS."""
    slm_names = {row[0] for row in slm_role.SYSTEM_PERMISSIONS}
    all_role_perm_names: set[str] = set()
    for role_def in slm_role.SYSTEM_ROLES.values():
        all_role_perm_names.update(role_def.get("permissions", []))
    unknown = all_role_perm_names - slm_names
    assert not unknown, f"SYSTEM_ROLES references permission names not in SYSTEM_PERMISSIONS: {unknown}"


def test_slm_role_permissions_align_with_shared(slm_role):
    """Each shared role's ROLE_PERMISSIONS must be a subset of the SLM SYSTEM_ROLES entry.

    This is the canonical drift detector (GH #6511): a developer adds a permission
    to ROLE_PERMISSIONS[Role.X] in the shared module but forgets to update
    SYSTEM_ROLES['x'] in the SLM backend → this test fails immediately.
    """
    role_name_map = {
        Role.ADMIN: "admin",
        Role.OPERATOR: "operator",
        Role.ANALYST: "analyst",
        Role.EDITOR: "editor",
        Role.USER: "user",
        Role.READONLY: "readonly",
    }
    gaps: dict[str, set[str]] = {}
    for shared_role, slm_key in role_name_map.items():
        if slm_key not in slm_role.SYSTEM_ROLES:
            continue
        shared_perms = {p.value if isinstance(p, Permission) else p for p in ROLE_PERMISSIONS[shared_role]}
        slm_perms = set(slm_role.SYSTEM_ROLES[slm_key]["permissions"])
        missing_in_slm = shared_perms - slm_perms
        if missing_in_slm:
            gaps[slm_key] = missing_in_slm

    if gaps:
        lines = [f"  [{role}] {p}" for role, perms in sorted(gaps.items()) for p in sorted(perms)]
        pytest.fail(
            "Shared ROLE_PERMISSIONS defines permissions absent from SLM SYSTEM_ROLES:\n"
            + "\n".join(lines)
            + "\nUpdate SYSTEM_ROLES in user_management/models/role.py to match."
        )
