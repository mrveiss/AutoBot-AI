# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one ``actor_id`` helper: stored attribution is unchanged, a missing id is a 401 (#15754)."""

import uuid

import pytest
from fastapi import HTTPException

from llc.api import _common, contacts, roles, workflows

_U = uuid.UUID("11111111-1111-4111-8111-111111111111")
_V = uuid.UUID("22222222-2222-4222-8222-222222222222")


def _before(current_user: dict) -> uuid.UUID:
    """The body all three copies carried before the merge."""
    raw = current_user.get("id") or current_user.get("user_id")
    return uuid.UUID(str(raw))


@pytest.mark.parametrize(
    "current_user",
    [
        {"id": str(_U)},
        {"user_id": str(_V)},
        {"id": str(_U), "user_id": str(_V)},
        {"id": "", "user_id": str(_V)},
        {"id": _U},
        {"id": str(_U), "role": "admin", "is_system": True},
    ],
)
def test_resolved_id_is_identical_to_the_old_copies(current_user: dict) -> None:
    assert _common.actor_id(current_user) == _before(current_user)


@pytest.mark.parametrize("current_user", [{}, {"id": None}, {"id": ""}, {"role": "admin"}, {"id": "not-a-uuid"}])
def test_missing_or_unparseable_id_is_a_401_not_a_500(current_user: dict) -> None:
    with pytest.raises(ValueError):
        _before(current_user)  # the old behaviour: an unhandled ValueError
    with pytest.raises(HTTPException) as exc:
        _common.actor_id(current_user)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("module", [contacts, roles, workflows])
def test_the_route_modules_use_the_shared_helper(module) -> None:
    assert module.actor_id is _common.actor_id
    assert not hasattr(module, "_actor_id")
