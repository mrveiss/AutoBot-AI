# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ``connector:`` secret-name prefix is reserved for the connector credential writer (#17850)."""

import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api import envelope_secrets
from api.secrets_delete_outcome import CREATE_REFUSALS, checked_secret_name, error_for
from autobot_shared.secrets_vault import VaultKind, VaultRef
from services import secrets_coordinator
from services.credential_write import CONNECTOR_NAME_PREFIX, connector_secret_name
from services.secret_names import ReservedSecretNameError, is_reserved_secret_name
from services.secrets_coordinator import SecretsCoordinator

_NAME = connector_secret_name("c1")
_USER = uuid.uuid4()
_TYPE = "api_key"


@pytest.mark.parametrize(
    "name",
    [
        _NAME,
        "connector:x",
        " Connector:x",
        "CONNECTOR:x",
        "\tconnector:x",
        "ｃｏｎｎｅｃｔｏｒ：x",
    ],
)
def test_reserved_names_including_case_whitespace_and_width_tricks(name):
    assert is_reserved_secret_name(name)


@pytest.mark.parametrize("name", ["my-connector:x", "connectors:x", "connector", "", None, "db-password"])
def test_other_names_are_not_reserved(name):
    assert not is_reserved_secret_name(name)


def test_builder_uses_the_shared_prefix():
    assert connector_secret_name("c1") == f"{CONNECTOR_NAME_PREFIX}c1:auth"


def _coordinator():
    service = MagicMock()
    service.create = AsyncMock()
    return SecretsCoordinator(service=service), service


async def _create(coord, name):
    return await coord.create(
        MagicMock(),
        user_id=_USER,
        permissions=set(),
        owner_vault=VaultRef(VaultKind.USER, str(_USER)),
        name=name,
        secret_type=_TYPE,
        plaintext=b"v",
    )


@pytest.mark.parametrize("name", [_NAME, " Connector:c1:auth"])
async def test_user_create_is_refused_and_writes_nothing(name):
    coord, service = _coordinator()
    with pytest.raises(ReservedSecretNameError):
        await _create(coord, name)
    service.create.assert_not_awaited()


async def test_service_create_is_refused_and_writes_nothing():
    coord, service = _coordinator()
    with pytest.raises(ReservedSecretNameError):
        await coord.service_create(
            MagicMock(),
            owner_vault=VaultRef(VaultKind.SYSTEM),
            name=_NAME,
            secret_type=_TYPE,
            plaintext=b"v",
            service_id="svc",
        )
    service.create.assert_not_awaited()


async def test_ordinary_name_still_creates(monkeypatch):
    coord, service = _coordinator()
    coord._facts = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(secrets_coordinator, "authorize", lambda *_a, **_k: True)
    await _create(coord, "db-password")
    service.create.assert_awaited_once()


def test_refusal_is_the_fixed_409_through_the_canonical_table():
    assert ReservedSecretNameError in CREATE_REFUSALS
    for exc in (
        envelope_secrets._mapped(ReservedSecretNameError("x")),
        error_for(ReservedSecretNameError("x")),
    ):
        assert exc.status_code == 409
        assert "reserved" in exc.detail


def test_rename_into_the_prefix_is_409_and_other_renames_pass():
    with pytest.raises(HTTPException) as caught:
        checked_secret_name(" Connector:c1:auth")
    assert caught.value.status_code == 409
    assert checked_secret_name("db-password") == "db-password"


@pytest.mark.parametrize(
    "method",
    ["read", "list", "delete", "rotate", "maintenance_delete", "service_delete"],
)
def test_reading_deleting_and_listing_existing_rows_is_not_gated(method):
    """Existing user rows with the prefix stay readable, listable, rotatable and deletable: no name check there."""
    source = inspect.getsource(getattr(SecretsCoordinator, method))
    assert "refuse_reserved_secret_name" not in source
