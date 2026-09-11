# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
API-key scopes as bundles of ``Permission`` members (#16270, #16040).

``API_KEY_SCOPES`` (``autobot_shared/user_management/models/api_key.py``) is
the list a person picks from when creating a key: 14 colon strings.
``Permission`` is the platform's one vocabulary of authority: dot strings.
This module is the single place that says what each scope means in that
vocabulary. A key's authority is then its owner's role permissions
intersected with ``key_permissions(scopes)`` (#16040 AC2).

The mappings follow the owner's rulings recorded on #16270:

- chat, teams and webhooks got dedicated members;
- ``settings:*`` maps to ``admin.config.*``;
- ``users:*`` maps to ``admin.users.*``;
- ``admin:*`` is every member, mirroring ``Role.ADMIN``.
"""

from typing import Dict, FrozenSet, Set

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

#: Scopes that grant everything. These are the same two ``APIKey.has_scope``
#: treats as global.
_GLOBAL_SCOPES = frozenset({"*", "admin:*"})


def key_permissions(scopes: object) -> FrozenSet[Permission]:
    """Return the permissions a key's *scopes* grant, matched the way ``APIKey.has_scope`` matches.

    - An exact scope grants its bundle.
    - ``resource:*`` grants every bundle under that resource.
    - ``*`` or ``admin:*`` grants every member.
    - An unknown scope grants nothing.

    Fails **closed** on a malformed ``scopes`` value, for the reason
    ``has_scope`` gives (#16040). A scalar string is iterable, and walking it
    character by character must not grant anything.
    """
    if not isinstance(scopes, list):
        return frozenset()
    granted: Set[Permission] = set()
    for scope in scopes:
        if not isinstance(scope, str):
            continue
        if scope in _GLOBAL_SCOPES:
            return frozenset(Permission)
        if scope.endswith(":*"):
            prefix = scope[:-1]
            for name, bundle in SCOPE_PERMISSIONS.items():
                if name.startswith(prefix):
                    granted |= bundle
        else:
            granted |= SCOPE_PERMISSIONS.get(scope, frozenset())
    return frozenset(granted)
