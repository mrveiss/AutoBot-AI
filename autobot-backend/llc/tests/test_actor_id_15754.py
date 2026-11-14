# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared ``actor_id`` and error translators: stored attribution and responses unchanged (#15754)."""

import uuid

import pytest
from fastapi import HTTPException, status

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


# --- error translators (#15754): the shared ones answer exactly as the roles/contacts copies did.

_EXCS = [
    ValueError("bad input"),
    NotAuthorisedError("not allowed"),
    ToolRegistryUnavailable("registry empty"),
    ValueError(""),
]


def _old_bad_request(exc):
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _old_forbidden(exc):
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


def _old_unavailable(exc):
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@pytest.mark.parametrize(
    ("new", "old", "code"),
    [
        (_common.bad_request, _old_bad_request, 400),
        (_common.forbidden, _old_forbidden, 403),
        (_common.registry_unavailable, _old_unavailable, 503),
    ],
)
@pytest.mark.parametrize("exc", _EXCS)
def test_translators_answer_as_the_old_local_copies_did(new, old, code, exc) -> None:
    got, was = new(exc), old(exc)
    assert (got.status_code, got.detail) == (was.status_code, was.detail) == (code, str(exc))


@pytest.mark.parametrize("module", [contacts, roles])
@pytest.mark.parametrize("name", ["_bad_request", "_forbidden", "_unavailable"])
def test_no_local_translator_remains(module, name) -> None:
    assert not hasattr(module, name)
