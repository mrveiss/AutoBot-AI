# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
What an API key may do in the SLM (#16040).

The permission decision itself is the shared evaluator
(``autobot_shared.auth.permission_evaluator``, #18263); ``permission_allowed``
and ``key_scope_allows`` are re-exported from there. This module keeps the
SLM-specific halves: the owner's role and the legacy grace period.

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

from autobot_shared.auth.key_scopes import key_scope_allows  # noqa: F401 -- re-exported (#18263)
from autobot_shared.auth.permission_evaluator import permission_allowed  # noqa: F401 -- re-exported (#18263)
from autobot_shared.auth.permissions import Role
from autobot_shared.env_utils import env_int

#: Keys created before this date predate scope enforcement (#16040 AC5). Set it
#: to the day enforcement reached this deployment, if that was later.
API_KEY_SCOPES_ENFORCED_FROM = os.environ.get("AUTOBOT_API_KEY_SCOPES_ENFORCED_FROM", "2026-09-11")

#: How many days such a key keeps its owner's full authority before it must be
#: re-issued. The owner ruled 90 days.
API_KEY_LEGACY_GRACE_DAYS = env_int("AUTOBOT_API_KEY_LEGACY_GRACE_DAYS", 90)


def role_for_user(is_platform_admin: bool) -> Role:
    """Return the platform role an SLM account acts with. Sessions and API keys use this same rule."""
    return Role.ADMIN if is_platform_admin else Role.USER


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
