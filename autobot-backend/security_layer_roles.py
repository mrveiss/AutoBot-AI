# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Role normalisation shared by the security layer's permission and approval gates.

Split out of ``security_layer.py`` (#19807) so that file does not grow past its
size ceiling; ``security_layer`` re-exports every name here unchanged.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role, role_value

# Performance optimization: O(1) lookup for deprecated privileged roles (Issue #326)
DEPRECATED_PRIVILEGED_ROLES = {"god", "superuser", "root"}


def _normalise_role(user_role: str) -> str:
    """Canonical spelling of a role, for every lookup that keys on one (#13820).

    Deprecated privileged aliases resolve to ``admin`` here too. ``check_permission``
    already downgrades them via ``_handle_deprecated_role``, but the approval gate
    did not — so ``god`` cleared the shell-execution check through the downgrade
    and then found an empty permission list in ``_should_force_approval``, where no
    approval branch could fire. A HIGH-risk command therefore ran unapproved.
    Pre-existing; fixed here because this change makes the two gates share a
    resolver, and leaving one of them out is what created the gap in the first
    place. The audit entry stays with ``_handle_deprecated_role`` so a downgrade is
    still logged exactly once.

    Takes the role string via ``role_value`` so a ``Role`` **member** normalises
    to its value rather than to ``"role.admin"`` (#14944).
    """
    normalised = role_value(user_role).strip().lower()
    return Role.ADMIN.value if normalised in DEPRECATED_PRIVILEGED_ROLES else normalised


@lru_cache(maxsize=64)
def canonical_role_permissions(user_role: str) -> List[str]:
    """Permission values ``user_role`` holds in ``ROLE_PERMISSIONS`` (#13820).

    Case-insensitive, because every other role check in this codebase is and a
    role arriving as ``"Admin"`` must not resolve to nothing. ``check_permission``
    normalises once for *all* its sources, so this and the configured/default
    lookups always agree on who a role is — a normalisation applied to one source
    of three creates a second identity that holds some grants and not others.

    ``superadmin`` (#13854) resolves to admin's grants: its ``ROLE_PERMISSIONS``
    entry is derived from admin's (#19125, owner decision 2026-10-21), and every
    path agrees because one mapping says so.

    An unrecognised role yields ``[]`` — no grant, and no exception either.

    A ``Role`` member resolves the same as its value (#14944); it previously
    stringified to ``"role.admin"`` and yielded ``[]``. Note this function is
    ``lru_cache``d and a member does NOT share a cache entry with its value
    (``lru_cache`` fast-paths exact ``str`` only), so the two were cached
    separately and the wrong answer was deterministic, not call-order dependent.
    """
    normalised = role_value(user_role).strip().lower()
    if not normalised:
        return []
    try:
        role = Role(normalised)
    except ValueError:
        return []
    return [p.value if isinstance(p, Permission) else str(p) for p in ROLE_PERMISSIONS.get(role, [])]
