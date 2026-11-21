# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ``connector:`` secret-name prefix is reserved for the connector credential writer (#17850)."""

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


_SYSTEM = VaultRef(VaultKind.SYSTEM, None)


def _existing_row_coordinator(monkeypatch):
    """A coordinator whose authorization seams admit everyone, over a mocked service holding a `connector:` row."""
    from models.secret import Secret
    from services import secrets_coordinator as module
    from testkit.fake_async_session import FakeAsyncSession

    row = Secret(
        id=uuid.uuid4(),
        name=_NAME,
        owner_id=_USER,
        scope="user",
        session_id=None,
        team_ids=[],
        shared_with=[],
        sealed_value={"ciphertext": "x", "nonce": "y"},
    )
    service = MagicMock()
    for name in ("read", "rotate_value", "delete"):
        setattr(service, name, AsyncMock(return_value=b"v" if name == "read" else row))
    service.list_for_vaults = AsyncMock(return_value=[row])
    coord = SecretsCoordinator(service=service)
    facts = MagicMock()
    facts.accessible_vaults.return_value = [_SYSTEM]
    monkeypatch.setattr(coord, "_facts", AsyncMock(return_value=facts))
    monkeypatch.setattr(coord, "_owner_vault", AsyncMock(return_value=_SYSTEM))
    monkeypatch.setattr(coord, "_load_maintenance_actor", AsyncMock())
    monkeypatch.setattr(coord, "_require_system_owner", AsyncMock())
    monkeypatch.setattr(coord, "_directly_granted_ids", AsyncMock(return_value=set()))
    monkeypatch.setattr(SecretsCoordinator, "_scope_permits", staticmethod(lambda *a: True))
    monkeypatch.setattr(module, "authorize", lambda *a, **k: True)
    monkeypatch.setattr(module, "audit_maintenance", AsyncMock())
    return coord, service, FakeAsyncSession(on_get=lambda _model, _pk: row), row


@pytest.mark.parametrize(
    ("method", "service_call"),
    [
        ("read", "read"),
        ("list", "list_for_vaults"),
        ("rotate", "rotate_value"),
        ("delete", "delete"),
        ("maintenance_delete", "delete"),
        ("service_delete", "delete"),
    ],
)
async def test_existing_connector_rows_are_not_gated(monkeypatch, method, service_call):
    """Every op on an existing `connector:` row reaches the service and never raises the name refusal."""
    coord, service, session, row = _existing_row_coordinator(monkeypatch)
    calls = {
        "read": dict(user_id=_USER, permissions=set(), secret_id=row.id),
        "list": dict(user_id=_USER, permissions=set()),
        "rotate": dict(user_id=_USER, permissions=set(), secret_id=row.id, new_plaintext=b"n"),
        "delete": dict(user_id=_USER, permissions=set(), secret_id=row.id),
        "maintenance_delete": dict(actor=MagicMock(), secret_id=row.id),
        "service_delete": dict(secret_id=row.id, vault=_SYSTEM),
    }

    try:
        await getattr(coord, method)(session, **calls[method])
    except ReservedSecretNameError:  # pragma: no cover -- the failure this test exists to catch
        pytest.fail(f"{method} refused an existing connector-named row")

    getattr(service, service_call).assert_awaited_once()
