# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The grants #16270 recorded for its new Permission members, pinned role by role.

- ``chat.use`` and ``chat.history`` are behaviour-preserving. Chat routes are
  login-only today, so every role that can log in holds them.
- ``teams.*`` and ``webhooks.trigger`` are a policy choice: admin only.
- ``superadmin`` holds none of them, because it holds no granular permissions
  by design (#13854).
"""

import pytest

from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role

_CHAT = {Permission.CHAT_USE, Permission.CHAT_HISTORY}
_ADMIN_ONLY = {
    Permission.TEAMS_READ,
    Permission.TEAMS_CREATE,
    Permission.TEAMS_MANAGE,
    Permission.TEAMS_DELETE,
    Permission.WEBHOOKS_TRIGGER,
}
_LOGIN_ROLES = [Role.ADMIN, Role.OPERATOR, Role.ANALYST, Role.EDITOR, Role.USER, Role.READONLY]


@pytest.mark.parametrize("role", _LOGIN_ROLES, ids=lambda r: r.value)
def test_every_role_that_can_log_in_keeps_chat(role):
    assert _CHAT <= set(ROLE_PERMISSIONS[role]), f"{role.value} lost chat"


def test_team_and_webhook_permissions_are_admin_only():
    holders = {role.value for role, perms in ROLE_PERMISSIONS.items() if _ADMIN_ONLY & set(perms)}
    assert holders == {Role.ADMIN.value}, f"held beyond admin: {holders}"


def test_superadmin_gains_none_of_them():
    assert not (_CHAT | _ADMIN_ONLY) & set(ROLE_PERMISSIONS[Role.SUPERADMIN])


def test_the_roles_listed_here_are_every_role_but_superadmin():
    """Keeps the chat check above from going vacuous when a role is added."""
    assert set(_LOGIN_ROLES) == set(Role) - {Role.SUPERADMIN}
