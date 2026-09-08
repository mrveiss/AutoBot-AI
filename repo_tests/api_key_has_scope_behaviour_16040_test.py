# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Behaviour of ``APIKey.has_scope``, which decides an authorisation (#16040).

``get_api_key_user`` now derives a key's ``admin`` flag as
``user.is_platform_admin and api_key.has_scope("admin:*")``. That AND is exactly
as strong as ``has_scope``, and ``has_scope`` had **no tests anywhere in the
repository** — ``grep -rln "has_scope" --include=*test*.py`` returned nothing.
A function nothing pins, load-bearing for a privilege decision.

**The input class that inverts the fix.** Every branch of ``has_scope`` is a
membership test, and ``in`` against a *string* is a substring test:

    "*" in ["read:users"]   -> False     (list: membership)
    "*" in "read:*"         -> True      (string: substring)

So a scalar ``scopes`` makes ``has_scope`` answer ``True`` to every scope it is
asked about, collapsing the new AND back to ``is_platform_admin`` alone — the
exact defect #16040 fixed, restored silently and in the direction of more
privilege.

**Why that is worth guarding rather than dismissing.** ``scopes`` is
``Mapped[list]`` over ``JSONB``. An annotation is not a database constraint and
JSONB stores a scalar happily, so the list-ness is guaranteed by whoever writes
the row. The HTTP path *is* defended — ``APIKeyCreate.scopes: List[str]``
validates at the boundary before ``_build_api_key`` runs — so this is not
reachable through the API today. A migration, a backfill, a fixture or a second
writer is not defended, and the failure would be invisible: the key authenticates
normally and simply has more authority than the console shows.

These tests construct the model directly rather than through the service, because
the service is the path that is already safe. The point is what the method does
when handed a value the service would never produce.
"""

from __future__ import annotations

import pytest

from autobot_shared.user_management.models.api_key import APIKey


class _Key:
    """Something carrying only `scopes`, for calling the real method against.

    `has_scope` is invoked unbound — `APIKey.has_scope(self, scope)` — so this
    exercises the shipped function body without instantiating a mapped class.
    That is deliberate on two counts: constructing `APIKey` requires the whole
    ORM registry to resolve (`User` must already be imported or the mapper
    raises), which would make this suite fail for a reason unrelated to scopes;
    and the service path is not what is under test here. The service validates.
    The question is what the method does with a value that bypassed it.
    """

    def __init__(self, scopes) -> None:
        self.scopes = scopes


def _has(scopes, scope: str) -> bool:
    return APIKey.has_scope(_Key(scopes), scope)


@pytest.mark.parametrize(
    "scopes,scope,expected",
    [
        # Exact match.
        (["chat:use"], "chat:use", True),
        (["chat:use"], "chat:read", False),
        # Wildcard: `chat:*` covers `chat:use`, and does not leak across resources.
        (["chat:*"], "chat:use", True),
        (["chat:*"], "admin:*", False),
        (["chat:*"], "billing:use", False),
        # Global admin, both spellings.
        (["*"], "anything:at:all", True),
        (["admin:*"], "chat:use", True),
        # A narrow key must not answer True to admin. This is the pairing the
        # whole fix rests on: it is what stops a scope-narrowed key carrying
        # platform-admin authority.
        (["chat:use"], "admin:*", False),
        (["read:users"], "admin:*", False),
        # Empty and absent.
        ([], "chat:use", False),
        ([], "admin:*", False),
    ],
)
def test_scope_matching(scopes, scope, expected) -> None:
    assert _has(scopes, scope) is expected


@pytest.mark.parametrize(
    "malformed",
    [
        "read:*",          # the inverting case: "*" in "read:*" is True as a substring
        "admin:*",
        "*",
        "",
        None,
        {"chat": "use"},   # dict membership tests keys, not values
        ("chat:use",),     # a tuple would work by luck, not by contract
        42,
    ],
)
def test_a_malformed_scopes_value_grants_nothing(malformed) -> None:
    """Fail closed. A non-list must never widen authority.

    `"read:*"` is the case that matters: as a string it makes the global-admin
    branch true, so before the guard this returned True for *every* scope asked.
    """
    assert _has(malformed, "admin:*") is False
    assert _has(malformed, "chat:use") is False
    assert _has(malformed, "*") is False


def test_the_substring_trap_is_real_and_not_hypothetical() -> None:
    """Pin the language behaviour this guard exists for.

    If this ever stops being true, the guard above is protecting against nothing
    and someone should find out from a test rather than by reasoning about it.
    """
    assert ("*" in "read:*") is True, "substring membership changed; re-derive the guard"
    assert ("*" in ["read:*"]) is False, "list membership changed; re-derive the guard"


def test_a_list_scopes_value_is_unaffected_by_the_guard() -> None:
    """The fail-closed path must not weaken the normal one.

    A guard that fixed the malformed case by breaking the ordinary one would pass
    every test above that only checks denials.
    """
    assert _has(["admin:*"], "admin:*") is True
    assert _has(["chat:*"], "chat:use") is True
