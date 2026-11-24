# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The canonical principal resolver and its 401 guard (#13688, #21655)."""

import pytest
from fastapi import HTTPException

from autobot_shared.principal import require_principal_id, resolve_principal_id


@pytest.mark.parametrize(
    "user, expected",
    [
        ({"id": "a", "user_id": "b", "sub": "c"}, "a"),
        ({"user_id": "b", "sub": "c"}, "b"),
        ({"sub": "c"}, "c"),
        ({"user_id": "", "sub": "c"}, "c"),
    ],
)
def test_resolve_follows_the_claim_order(user, expected):
    assert resolve_principal_id(user) == expected


@pytest.mark.parametrize("user", [None, {}, {"username": "alice"}, {"user_id": "", "sub": ""}])
def test_require_refuses_a_caller_without_identity(user):
    """A username is mutable and never an owner, and an empty claim is no claim: both get a 401."""
    assert resolve_principal_id(user) is None
    with pytest.raises(HTTPException) as exc:
        require_principal_id(user)
    assert exc.value.status_code == 401


def test_require_returns_the_same_id_the_resolver_does():
    user = {"user_id": "u-1", "sub": "s-1", "username": "alice"}
    assert require_principal_id(user) == resolve_principal_id(user) == "u-1"
