# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical resolution of an authenticated principal's owner id (#13688).

Lives in ``autobot_shared`` deliberately: it is a pure dict read with no
imports, needed by both the API layer and the memory data plane, and it must
stay importable without dragging in the config/Redis chain that
``auth_middleware`` pulls at import time.

Before this, call sites each picked their own claim order — the repo carried
roughly six competing variants. Reading the wrong one is not cosmetic: the
``user_id`` claim is set only when a token carries it
(``auth_middleware._extract_user_from_jwt``), while ``sub`` is set
unconditionally, so a call site keying on ``user_id`` alone silently drops
principals and can file one user's rows under two different owners.
"""

from typing import Any, Dict, Optional

# Claim order: `id` (user_management records) → `user_id` (optional JWT claim)
# → `sub` (always present on a JWT principal).
_CLAIM_ORDER = ("id", "user_id", "sub")


def resolve_principal_id(current_user: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return the principal's owner id, or None when it has no user identity.

    None is returned for internal service keys and dev-header auth, which are
    authenticated but are not a *user*. Callers decide what that means — a 401
    for a user-facing endpoint, or a system-owned write for background work.
    It is never a valid owner scope.
    """
    if not current_user:
        return None
    for claim in _CLAIM_ORDER:
        value = current_user.get(claim)
        if value:
            return str(value)
    return None


def require_principal_id(current_user: Optional[Dict[str, Any]]) -> str:
    """Return the principal's owner id, or raise a 401 when it has no user identity.

    For user-facing routes that scope data by owner: an identity-less caller must
    never fall back to a shared scope such as ``""`` or ``None`` (#21655).
    """
    owner = resolve_principal_id(current_user)
    if not owner:
        from fastapi import HTTPException  # lazy: keep this module import-free (see the module docstring)

        raise HTTPException(status_code=401, detail="User identity required")
    return owner


def resolve_actor_id(current_user: Optional[Dict[str, Any]]) -> Optional[str]:
    """The stable id to record as the *actor* of an audited action, or None when there is none.

    A human principal resolves to its owner id (``resolve_principal_id``). An admitted service principal
    (``service: True``, minted by ``auth_service_opt_in.admit_service``) resolves to its stable
    ``service:<caller>`` name, which is not a user id and so is never an owner scope. Anything else, including a
    bare ``username``, resolves to None: a mutable name is not an identity (#22222).
    """
    human = resolve_principal_id(current_user)
    if human or not current_user:
        return human
    name = current_user.get("username")
    if current_user.get("service") is True and isinstance(name, str) and name:
        return name
    return None


def require_actor_id(current_user: Optional[Dict[str, Any]]) -> str:
    """``resolve_actor_id``, or a 401 when the caller is neither a human principal nor an admitted service."""
    actor = resolve_actor_id(current_user)
    if not actor:
        from fastapi import HTTPException  # lazy: keep this module import-free (see the module docstring)

        raise HTTPException(status_code=401, detail="User identity required")
    return actor


__all__ = ["require_actor_id", "require_principal_id", "resolve_actor_id", "resolve_principal_id"]
