# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
The SLM's permission decision, including what an API key may do (#16040).

Kept free of FastAPI so the whole decision can be unit-tested directly.
``services/auth.py`` turns a refusal into a 403 and wires the key handling
into ``get_api_key_user``.

- **AC2: intersection.** A key-authenticated caller may exercise a permission
  only if its owner's role grants it AND the key's scopes carry it
  (``autobot_shared.auth.key_scopes``). A key can never exceed its owner, nor
  its own scopes.
- **AC5: keys that predate enforcement.** Owner ruling, 2026-09-11. Such a key
  keeps its owner's full authority, with a warning on every use, for a grace
  period. After that it is refused until it is re-issued with explicit scopes.
  The cutoff and the grace period are env-backed, so they can move without a
  code change.
"""

import os
from datetime import datetime, timedelta, timezone

from autobot_shared.auth.key_scopes import key_permissions
from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role

#: Keys created before this date predate scope enforcement (#16040 AC5). Set it
#: to the day enforcement reached this deployment, if that was later.
API_KEY_SCOPES_ENFORCED_FROM = os.environ.get("AUTOBOT_API_KEY_SCOPES_ENFORCED_FROM", "2026-09-11")

#: How many days such a key keeps its owner's full authority before it must be
#: re-issued. The owner ruled 90 days.
API_KEY_LEGACY_GRACE_DAYS = int(os.environ.get("AUTOBOT_API_KEY_LEGACY_GRACE_DAYS", "90"))


def role_for_user(is_platform_admin: bool) -> Role:
    """Return the platform role an SLM account acts with. Sessions and API keys use this same rule."""
    return Role.ADMIN if is_platform_admin else Role.USER


def resolve_role(caller: dict) -> Role:
    """Return the caller's platform role, from the ``role`` claim or else the legacy ``admin`` flag.

    Moved from ``services/auth.py`` (``_resolve_role``) together with the rest
    of the decision (#16040), so it can be tested without FastAPI. An
    unrecognised role resolves to USER.
    """
    role_str = caller.get("role")
    if role_str:
        try:
            return Role(role_str)
        except ValueError:
            return Role.USER
    return Role.ADMIN if caller.get("admin", False) else Role.USER


def _as_utc(moment: datetime) -> datetime:
    """Treat a naive timestamp as UTC, which is what the models store."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def legacy_grace_deadline(
    created_at: datetime | None,
    *,
    enforced_from: str = API_KEY_SCOPES_ENFORCED_FROM,
    grace_days: int = API_KEY_LEGACY_GRACE_DAYS,
) -> datetime | None:
    """Return when a pre-enforcement key's grace ends, or None if the key is subject to its scopes.

    A key with no ``created_at`` is treated as subject to its scopes. That
    fails closed: an unknown age must not buy full authority.
    """
    cutoff = _as_utc(datetime.fromisoformat(enforced_from))
    if created_at is None or _as_utc(created_at) >= cutoff:
        return None
    return cutoff + timedelta(days=grace_days)


def key_scope_allows(key_payload: dict, permission: Permission) -> bool:
    """Return whether an API-key caller's scopes carry *permission*. This is the key half of AC2.

    A pre-enforcement key in its grace period (``legacy_full_scope``) carries
    its owner's full role (AC5). A malformed ``scopes`` value carries nothing.
    """
    if key_payload.get("legacy_full_scope") is True:
        return True
    return permission in key_permissions(key_payload.get("scopes"))


def permission_allowed(caller: dict, permission: Permission) -> bool:
    """Make the whole decision that ``require_permission`` and ``require_key_permission`` apply.

    The caller's role must grant *permission*. If the caller authenticated with
    an API key, the key's scopes must also carry it (AC2).
    """
    if permission not in ROLE_PERMISSIONS.get(resolve_role(caller), []):
        return False
    return "api_key_id" not in caller or key_scope_allows(caller, permission)
