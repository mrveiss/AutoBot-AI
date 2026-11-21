# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The create routes answer duplicate and differing creates with a fixed 409 (#17850); a repeat is a 200."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Response

from api import envelope_secrets, secrets_system_vault
from api.schemas_system import SecretCreateRequest
from api.secrets_delete_outcome import creation_status, error_for
from services.envelope_secrets_service import AmbiguousSecretError, SecretConflictError

_A, _B = uuid.UUID(int=1), uuid.UUID(int=2)
_BODY = envelope_secrets.CreateSecretBody(owner_vault="system", name="N", secret_type="api_key", value="v")
_REFUSALS = [
    AmbiguousSecretError("system", [_A, _B]),
    SecretConflictError("inactive", _A),
    SecretConflictError("value_differs", _A),
]


def _secret(already: bool):
    return SimpleNamespace(
        id=_A, name="N", type="api_key", owner_vault="system", version=1, already_existed=already,
        created_at=None, updated_at=None, scope="system", description=None, tags=[], is_active=True,
    )  # fmt: skip


@pytest.mark.parametrize("exc", _REFUSALS, ids=["ambiguous", "inactive", "value_differs"])
def test_each_conflict_is_a_fixed_409_that_names_the_way_out_and_no_id(exc):
    refusal = error_for(exc)
    assert refusal.status_code == 409
    assert str(_A) not in refusal.detail and "N" != refusal.detail
    assert {"ambiguous": "duplicates", "inactive": "delete it first", "value_differs": "rotate"}[
        exc_reason(exc)
    ] in refusal.detail


def exc_reason(exc) -> str:
    return "ambiguous" if isinstance(exc, AmbiguousSecretError) else exc.reason


@pytest.mark.parametrize("exc", _REFUSALS)
@pytest.mark.asyncio
async def test_the_user_create_route_maps_a_conflict_to_409_not_500(exc):
    coordinator = MagicMock(create=AsyncMock(side_effect=exc))
    with pytest.raises(HTTPException) as raised:
        await envelope_secrets.create_secret(_BODY, Response(), (_A, set()), AsyncMock(), coordinator)
    assert raised.value.status_code == 409


@pytest.mark.parametrize("exc", _REFUSALS)
@pytest.mark.asyncio
async def test_the_service_create_route_maps_a_conflict_to_409_not_500(exc, monkeypatch):
    coordinator = MagicMock(service_create=AsyncMock(side_effect=exc))
    monkeypatch.setattr(envelope_secrets, "_require_system_vault", lambda vault, service_id: None)
    with pytest.raises(HTTPException) as raised:
        await envelope_secrets.service_create_system_secret(_BODY, Response(), "svc", AsyncMock(), coordinator)
    assert raised.value.status_code == 409


@pytest.mark.parametrize("exc", _REFUSALS)
@pytest.mark.asyncio
async def test_the_system_visibility_create_maps_a_conflict_to_409_not_500(exc, monkeypatch):
    coordinator = MagicMock(create=AsyncMock(side_effect=exc))

    async def one_session():
        yield AsyncMock()

    monkeypatch.setattr("api.envelope_secrets.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("llc.deps.get_session", one_session)
    monkeypatch.setattr(secrets_system_vault, "_principal", AsyncMock(return_value=(_A, {"admin"})))
    request = SecretCreateRequest(name="N", value="v", type="api_key", scope="shared", visibility="system")
    with pytest.raises(HTTPException) as raised:
        await secrets_system_vault.create_system_vault_secret(request, "owner")
    assert raised.value.status_code == 409


@pytest.mark.asyncio
async def test_a_repeat_of_the_same_value_answers_200_and_a_new_secret_201():
    for already, expected in ((True, 200), (False, 201)):
        response = Response()
        coordinator = MagicMock(create=AsyncMock(return_value=_secret(already)))
        await envelope_secrets.create_secret(_BODY, response, (_A, set()), AsyncMock(), coordinator)
        assert response.status_code == expected == creation_status(_secret(already))
