# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared ``actor_id`` and error translators: stored attribution and responses unchanged (#15754)."""

import uuid

import pytest
from fastapi import HTTPException

from llc.api import _common, contacts, roles, workflows
from llc.services.authz import NotAuthorisedError
from llc.services.role_tool import ToolRegistryUnavailable

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


# --- error translators (#15754): the shared ones keep the status codes the roles/contacts copies answered with.
# Their text no longer follows ``str(exc)`` (#21579); ``test_llc_common_refusals_21579.py`` covers it.

_EXCS = [
    ValueError("bad input"),
    NotAuthorisedError("not allowed"),
    ToolRegistryUnavailable("registry empty"),
    ValueError(""),
]


@pytest.mark.parametrize(
    ("new", "code"),
    [
        (_common.bad_request, 400),
        (_common.forbidden, 403),
        (_common.registry_unavailable, 503),
    ],
)
@pytest.mark.parametrize("exc", _EXCS)
def test_translators_keep_the_old_local_copies_status_codes(new, code, exc) -> None:
    assert new(exc).status_code == code


@pytest.mark.parametrize("module", [contacts, roles])
@pytest.mark.parametrize("name", ["_bad_request", "_forbidden", "_unavailable"])
def test_no_local_translator_remains(module, name) -> None:
    assert not hasattr(module, name)
