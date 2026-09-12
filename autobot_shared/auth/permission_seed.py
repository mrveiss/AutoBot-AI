# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Database seeding rows, generated from the canonical permission sources (#6511).

Split out of ``permissions.py`` (#16270). That file was frozen at its
file-size ceiling and needed room for new ``Permission`` members.

The builders take the canonical sources as arguments rather than importing
them. So this module imports nothing from ``permissions`` (no import cycle),
and it pulls in no bcrypt or JWT dependency (``lazy_import_test.py``, #14397).

``permissions.py`` still computes ``SYSTEM_PERMISSIONS`` and ``SYSTEM_ROLES``
once and exports them. Every ``from autobot_shared.auth.permissions import
SYSTEM_PERMISSIONS`` keeps working, and so does the SLM parity test's identity
check.
"""

from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Sequence, TypeVar

#: The role type. ``Mapping`` is invariant in its key type, so a
#: ``dict[Role, ...]`` is not a ``Mapping[Enum, ...]``. A TypeVar lets
#: ``permissions.Role`` flow through without this module importing it.
_RoleT = TypeVar("_RoleT", bound=Enum)

# Legacy colon-style secrets vault permissions required by secrets_authz policy
# (#10088). They are not in the Permission enum (colon composite names), but
# they must appear in SYSTEM_PERMISSIONS and the relevant SYSTEM_ROLES entries.
_SECRETS_VAULT_LEGACY: List[tuple] = [
    ("secrets:team:read", "secrets", "team:read", "Read team-vault secrets"),
    ("secrets:team:write", "secrets", "team:write", "Write team-vault secrets"),
    ("secrets:team:share", "secrets", "team:share", "Share team-vault secrets"),
    ("secrets:team:revoke", "secrets", "team:revoke", "Revoke team-vault secret grants"),
    ("secrets:role:read", "secrets", "role:read", "Read role-vault secrets"),
    ("secrets:role:write", "secrets", "role:write", "Write role-vault secrets"),
    ("secrets:role:share", "secrets", "role:share", "Share role-vault secrets"),
    ("secrets:role:revoke", "secrets", "role:revoke", "Revoke role-vault secret grants"),
]

_SECRETS_ADMIN_PERMS: List[str] = [row[0] for row in _SECRETS_VAULT_LEGACY]
_SECRETS_USER_PERMS: List[str] = [
    "secrets:team:read",
    "secrets:team:write",
    "secrets:role:read",
    "secrets:role:write",
]

#: The roles, by value, that carry legacy secrets permissions on top of their
#: ROLE_PERMISSIONS entry.
_SECRETS_EXTRA_BY_ROLE: Dict[str, List[str]] = {"admin": _SECRETS_ADMIN_PERMS, "user": _SECRETS_USER_PERMS}


def _perm_description(perm: Enum) -> str:
    """Generate a human-readable description from a dot-style permission value."""
    parts = perm.value.split(".")
    resource = ".".join(parts[:-1]) if len(parts) > 1 else perm.value
    action = parts[-1] if len(parts) > 1 else perm.value
    return f"{action.capitalize()} {resource}"


def build_system_permissions(permissions: Iterable[Enum]) -> List[tuple]:
    """Generate SYSTEM_PERMISSIONS from the canonical Permission enum.

    Each entry is ``(name, resource, action, description)``. The ``name``
    field equals the Permission enum value (dot-style), which makes it the
    primary key used by DB seeding and the parity tests. The legacy
    colon-style ``secrets:*`` entries are appended because the secrets_authz
    policy uses names that the dot-style enum can't represent (#10088).
    """
    rows: List[tuple] = []
    for perm in permissions:
        parts = perm.value.split(".")
        resource = ".".join(parts[:-1]) if len(parts) > 1 else perm.value
        action = parts[-1] if len(parts) > 1 else perm.value
        rows.append((perm.value, resource, action, _perm_description(perm)))
    rows.extend(_SECRETS_VAULT_LEGACY)
    return rows


def build_system_roles(
    role_permissions: Mapping[_RoleT, Sequence[Any]], role_meta: Mapping[_RoleT, Dict]
) -> Dict[str, Dict]:
    """Generate SYSTEM_ROLES from ROLE_PERMISSIONS.

    Each role entry carries every dot-style permission from ROLE_PERMISSIONS,
    plus the legacy colon-style ``secrets:*`` permissions that secrets_authz
    requires (#10088). The priority and description come from *role_meta*,
    which is ``permissions._ROLE_META``.
    """
    result: Dict[str, Dict] = {}
    for role, perms in role_permissions.items():
        meta = role_meta.get(role, {"description": role.value, "priority": 0})
        result[role.value] = {
            "description": meta["description"],
            "priority": meta["priority"],
            "permissions": [getattr(p, "value", p) for p in perms] + _SECRETS_EXTRA_BY_ROLE.get(role.value, []),
        }
    return result
