# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE permission decision both services apply (#18263, owner ruling 2026-10-11: strict union).

A caller may exercise a ``Permission`` when

    (ROLE_PERMISSIONS[caller role]  UNION  DB custom-role grants of the caller)
    AND the API-key scope narrowing (#16040), for a key caller.

Every input is read strictly; anything this module cannot resolve grants nothing:

- **Role.** The ``role`` claim must be exactly a ``Role`` value. No lower-casing, no
  legacy ``admin``-flag fallback, no "unknown role means user". Where the two
  services disagreed, the stricter reading was kept (the decision-change table
  is on #18263).
- **DB grants.** Permission names from the caller's DB roles (#18259) count only
  when they are a ``Permission`` value, and only in scope (#18338): a system role's
  grants everywhere, a company role's only when the caller's ``org_id`` is that
  company. ``allow_all`` and other free-form names grant nothing here. They are
  looked up only for a caller carrying a UUID ``user_id``, and only when the role
  grant has not already decided.
- **Key narrowing.** A caller with ``api_key_id`` is also bounded by its scopes
  (``key_scopes.key_scope_allows``), so a key never exceeds its owner or itself.
"""

import uuid
from typing import Awaitable, Callable, Iterable

from autobot_shared.auth.key_scopes import key_scope_allows
from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role

#: Loads the permission names a user holds through DB roles, acting in an org (or None).
#: Injected for tests; the default is the shared RBAC middleware's cached lookup.
DbGrantLoader = Callable[[uuid.UUID, uuid.UUID | None], Awaitable[Iterable[str]]]

_PERMISSION_VALUES = frozenset(member.value for member in Permission)


def role_grant(caller: object) -> frozenset[Permission]:
    """The permissions ``ROLE_PERMISSIONS`` grants the caller's exact ``role`` claim."""
    role = caller.get("role") if isinstance(caller, dict) else None
    if not isinstance(role, str):
        return frozenset()
    try:
        resolved = Role(role)
    except ValueError:
        return frozenset()
    return frozenset(ROLE_PERMISSIONS.get(resolved, ()))


def db_grant(names: Iterable[str]) -> frozenset[Permission]:
    """The ``Permission`` members among DB permission *names*; any other name grants nothing."""
    return frozenset(Permission(name) for name in names if isinstance(name, str) and name in _PERMISSION_VALUES)


def _claim_uuid(caller: object, claim: str) -> uuid.UUID | None:
    """The caller's *claim* as a UUID, or None when it is absent or not a UUID."""
    raw = caller.get(claim) if isinstance(caller, dict) else None
    if isinstance(raw, uuid.UUID):
        return raw
    try:
        return uuid.UUID(str(raw)) if raw else None
    except ValueError:
        return None


def caller_user_id(caller: object) -> uuid.UUID | None:
    """The caller's ``user_id`` as a UUID, or None."""
    return _claim_uuid(caller, "user_id")


def caller_org_id(caller: object) -> uuid.UUID | None:
    """The org the caller acts in (``org_id`` claim) as a UUID, or None: platform grants only (#18338)."""
    return _claim_uuid(caller, "org_id")


def key_narrowing_allows(caller: object, permission: Permission) -> bool:
    """True for a non-key caller; for an API-key caller, whether its scopes carry *permission*."""
    if not isinstance(caller, dict) or "api_key_id" not in caller:
        return isinstance(caller, dict)
    return key_scope_allows(caller, permission)


def permission_allowed(caller: object, permission: Permission, db_names: Iterable[str] = ()) -> bool:
    """The whole decision, given the caller's DB permission names (default: none)."""
    require_permission_member(permission)
    granted = permission in role_grant(caller) or permission in db_grant(db_names)
    return granted and key_narrowing_allows(caller, permission)


def require_permission_member(permission: object) -> None:
    """Reject a non-``Permission`` argument: a string here is how the forks drifted."""
    if not isinstance(permission, Permission):
        raise TypeError(f"permission must be a Permission member, got {type(permission).__name__}: {permission!r}")


async def default_db_loader(user_id: uuid.UUID, org_id: uuid.UUID | None) -> Iterable[str]:
    """Read the caller's in-scope DB grants through the shared, cached RBAC middleware (#18259, #18338)."""
    from autobot_shared.user_management.middleware.rbac_middleware import rbac_middleware  # noqa: PLC0415

    return await rbac_middleware.get_user_permissions(user_id, org_id)


async def evaluate_any(
    caller: object, permissions: Iterable[Permission], load_db_names: DbGrantLoader | None = None
) -> bool:
    """Whether the caller may exercise at least one of *permissions*.

    DB grants are loaded at most once, and only when no role grant decides.
    """
    wanted = tuple(permissions)
    for permission in wanted:
        require_permission_member(permission)
    if any(permission_allowed(caller, permission) for permission in wanted):
        return True
    user_id = caller_user_id(caller)
    if user_id is None:
        return False
    names = tuple(await (load_db_names or default_db_loader)(user_id, caller_org_id(caller)))
    return any(permission_allowed(caller, permission, names) for permission in wanted)


async def evaluate_permission(
    caller: object, permission: Permission, load_db_names: DbGrantLoader | None = None
) -> bool:
    """Whether the caller may exercise *permission*: the single-permission form of ``evaluate_any``."""
    return await evaluate_any(caller, (permission,), load_db_names)
