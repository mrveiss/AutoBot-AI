# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
API-key scopes, and what each one grants in the ``Permission`` vocabulary (#16270, #16040).

``API_KEY_SCOPES`` (``autobot_shared/user_management/models/api_key.py``) is
the list a person picks from when creating a key: 14 colon strings.
``Permission`` is the platform's one vocabulary of authority: dot strings.
This module holds both halves of a key's authority in one place:

- ``scope_granted``: whether a key's scopes grant a scope. This is the ONE
  implementation of the matching rule; ``APIKey.has_scope`` delegates here.
- ``SCOPE_PERMISSIONS`` / ``key_permissions``: what those scopes mean as
  permissions. A key's authority is its owner's role permissions intersected
  with ``key_permissions(scopes)`` (#16040 AC2).

The mappings follow the owner's rulings recorded on #16270:

- chat, teams and webhooks got dedicated members;
- ``settings:*`` maps to ``admin.config.*``;
- ``users:*`` maps to ``admin.users.*``;
- ``admin:*`` is every member, mirroring ``Role.ADMIN``.
"""

from typing import Dict, FrozenSet

from autobot_shared.auth.permissions import Permission

#: Every published API-key scope and the permissions it grants.
#: ``key_scopes_test.py`` asserts that this covers ``API_KEY_SCOPES`` exactly
#: and that no bundle is empty.
SCOPE_PERMISSIONS: Dict[str, FrozenSet[Permission]] = {
    "chat:use": frozenset({Permission.CHAT_USE}),
    "chat:history": frozenset({Permission.CHAT_HISTORY}),
    "knowledge:read": frozenset({Permission.KNOWLEDGE_READ}),
    "knowledge:write": frozenset({Permission.KNOWLEDGE_WRITE}),
    "knowledge:delete": frozenset({Permission.KNOWLEDGE_DELETE}),
    "files:read": frozenset({Permission.FILES_VIEW, Permission.FILES_DOWNLOAD}),
    "files:write": frozenset({Permission.FILES_UPLOAD, Permission.FILES_MANAGE}),
    "files:delete": frozenset({Permission.FILES_DELETE}),
    "users:read": frozenset({Permission.ADMIN_USERS_READ}),
    "users:write": frozenset({Permission.ADMIN_USERS_WRITE}),
    "settings:read": frozenset({Permission.ADMIN_CONFIG_READ}),
    "settings:write": frozenset({Permission.ADMIN_CONFIG_WRITE}),
    "webhooks:trigger": frozenset({Permission.WEBHOOKS_TRIGGER}),
    "admin:*": frozenset(Permission),
}

#: Scopes that grant every other scope.
_GLOBAL_SCOPES = ("*", "admin:*")


def scope_granted(scopes: object, scope: str) -> bool:
    """Return whether a key holding *scopes* is granted *scope*. This is the one scope matcher (#16040).

    - An exact scope matches itself.
    - ``resource:*`` matches every scope under that resource; for example,
      ``chat:*`` matches ``chat:use``.
    - ``*`` or ``admin:*`` matches everything.

    ``APIKey.has_scope`` delegates here, and ``key_permissions`` is built on
    it. So the rule has exactly one implementation
    (``repo_tests/api_key_scopes_are_enforced_16040_test.py``).

    Fails **closed** on a malformed *scopes*. Every check below is a
    membership test, and ``in`` against a *string* is a substring test. A
    scalar ``"read:*"`` would therefore answer True to ``"*" in scopes`` and
    grant every scope, admin included: a silent failure, in the direction of
    more privilege. ``APIKey.scopes`` is ``Mapped[list]`` over ``JSONB``. The
    annotation is not a database constraint, so the type is guaranteed by
    whoever writes the row, not by the column.
    """
    held = scopes if isinstance(scopes, list) else []
    if scope in held:
        return True
    resource = scope.split(":")[0] if ":" in scope else scope
    if f"{resource}:*" in held:
        return True
    return any(global_scope in held for global_scope in _GLOBAL_SCOPES)


def key_permissions(scopes: object) -> FrozenSet[Permission]:
    """Return the permissions a key's *scopes* grant.

    That is every bundle whose scope ``scope_granted`` allows. An unknown scope,
    or a malformed *scopes* value, grants nothing.
    """
    return frozenset(
        permission for name, bundle in SCOPE_PERMISSIONS.items() if scope_granted(scopes, name) for permission in bundle
    )
