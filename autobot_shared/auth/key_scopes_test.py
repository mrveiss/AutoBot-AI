# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Scope bundles (#16270 AC2) and their agreement with ``APIKey.has_scope``."""

import pytest

from autobot_shared.auth.key_scopes import SCOPE_PERMISSIONS, key_permissions
from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role
from autobot_shared.user_management.models.api_key import API_KEY_SCOPES, APIKey


def test_every_published_scope_has_a_bundle_and_nothing_else_does():
    assert set(SCOPE_PERMISSIONS) == set(API_KEY_SCOPES), (
        f"published but unmapped: {sorted(set(API_KEY_SCOPES) - set(SCOPE_PERMISSIONS))}; "
        f"mapped but unpublished: {sorted(set(SCOPE_PERMISSIONS) - set(API_KEY_SCOPES))}"
    )


def test_no_scope_maps_to_an_empty_bundle():
    empty = sorted(scope for scope, bundle in SCOPE_PERMISSIONS.items() if not bundle)
    assert not empty, f"scopes that would grant nothing: {empty}"


def test_admin_star_is_exactly_what_the_admin_role_holds():
    assert SCOPE_PERMISSIONS["admin:*"] == frozenset(ROLE_PERMISSIONS[Role.ADMIN])


#: Key scope lists that exercise each matching rule.
_KEYS = [
    ["chat:use"],
    ["chat:*"],
    ["files:read", "knowledge:*"],
    ["settings:read", "users:write"],
    ["webhooks:trigger"],
    ["*"],
    ["admin:*"],
    ["not-a-scope"],
    [],
]


@pytest.mark.parametrize("key_scopes", _KEYS, ids=lambda s: ",".join(s) or "none")
def test_a_permission_is_granted_exactly_when_has_scope_grants_a_scope_that_carries_it(key_scopes):
    """``key_permissions`` must never disagree with ``has_scope``, the matcher that already authorises keys."""
    key = APIKey(scopes=key_scopes)
    expected = {p for scope, bundle in SCOPE_PERMISSIONS.items() if key.has_scope(scope) for p in bundle}
    assert key_permissions(key_scopes) == frozenset(expected)


def test_a_resource_wildcard_does_not_leak_into_other_resources():
    """The contrast case: ``chat:*`` grants chat, and nothing from files or admin."""
    granted = key_permissions(["chat:*"])
    assert granted == {Permission.CHAT_USE, Permission.CHAT_HISTORY}


@pytest.mark.parametrize("malformed", ["*", "admin:*", None, {"admin:*": True}, 7])
def test_a_malformed_scopes_value_grants_nothing(malformed):
    """A scalar ``"*"`` must not grant everything by being iterable (#16040)."""
    assert key_permissions(malformed) == frozenset()
