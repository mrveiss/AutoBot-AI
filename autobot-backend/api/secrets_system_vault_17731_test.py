# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PUT and DELETE reach the vault a SYSTEM-visibility secret was created in (#17099, #17731).

Create routed a SYSTEM secret to the envelope vault; update and delete only
touched the legacy file store, so the vault copy served a superseded value and
outlived its own deletion. These assert on the STORE, not the status code --
the response was 200 while the credential survived.
"""

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import secrets as secrets_module
from api import secrets_system_vault
from services.envelope_secrets_service import SecretAccessError

_ADMIN_ID = str(uuid.uuid4())
_SECRET_ID = str(uuid.uuid4())


class _FakeVault:
    """In-memory stand-in for SecretsCoordinator: admin-only SYSTEM writes."""

    def __init__(self, admin: bool = True):
        self.store: dict[uuid.UUID, bytes] = {uuid.UUID(_SECRET_ID): b"old-value"}
        self.admin = admin

    def _check(self):
        if not self.admin:
            raise SecretAccessError("not authorized to write in system")

    async def rotate(self, session, *, user_id, permissions, secret_id, new_plaintext):
        self._check()
        self.store[secret_id] = new_plaintext
        return SimpleNamespace(id=secret_id, name="n", type="api_key", owner_vault="system", version=2)

    async def delete(self, session, *, user_id, permissions, secret_id):
        self._check()
        del self.store[secret_id]

    async def list(self, session, *, user_id, permissions):
        row = dict(name="vault-key", type="api_key", owner_vault="system", version=1)
        other = dict(name="mine", type="api_key", owner_vault=f"user:{_ADMIN_ID}", version=1)
        sealed = b"SEALED-CIPHERTEXT"  # must never reach the response
        return [SimpleNamespace(id=i, sealed_value=sealed, **row) for i in self.store] + [
            SimpleNamespace(id=uuid.uuid4(), sealed_value=sealed, **other)
        ]


@pytest.fixture()
def client_and_vault(monkeypatch):
    def _make(admin: bool = True):
        vault = _FakeVault(admin)

        async def _one_session():
            yield MagicMock(commit=AsyncMock())

        legacy = MagicMock()
        legacy.update_secret.return_value = None
        legacy.delete_secret.return_value = False
        legacy.list_secrets.return_value = [{"id": "legacy-1", "name": "old"}]
        monkeypatch.setattr(secrets_module, "secrets_manager", legacy)
        monkeypatch.setattr(secrets_module, "audit_secret_op", AsyncMock())
        monkeypatch.setattr(secrets_module, "audit_record", MagicMock())
        monkeypatch.setattr(secrets_module, "check_rate_limit", AsyncMock())
        monkeypatch.setattr(
            secrets_module,
            "get_auth_middleware",
            lambda: SimpleNamespace(get_user_from_request=lambda _r: {"user_id": _ADMIN_ID}),
        )
        monkeypatch.setattr(secrets_system_vault, "_coordinator_or_none", lambda: vault)
        monkeypatch.setattr(secrets_system_vault, "_principal", AsyncMock(return_value=(uuid.UUID(_ADMIN_ID), set())))
        monkeypatch.setattr(
            secrets_system_vault, "_is_system_secret", AsyncMock(side_effect=lambda s, i: i in vault.store)
        )
        monkeypatch.setattr("llc.deps.get_session", _one_session)

        app = FastAPI()
        app.include_router(secrets_module.router, prefix="/api/secrets")
        app.dependency_overrides[secrets_module.check_admin_permission] = lambda: True
        return TestClient(app, raise_server_exceptions=False), vault

    return _make


def test_delete_removes_the_vault_copy(client_and_vault):
    client, vault = client_and_vault()
    response = client.delete(f"/api/secrets/{_SECRET_ID}")
    assert response.status_code == 200
    assert uuid.UUID(_SECRET_ID) not in vault.store


def test_update_replaces_the_vault_value(client_and_vault):
    client, vault = client_and_vault()
    response = client.put(f"/api/secrets/{_SECRET_ID}", json={"value": "new-value"})
    assert response.status_code == 200
    assert vault.store[uuid.UUID(_SECRET_ID)] == b"new-value"


def test_update_without_a_value_fails_closed_and_leaves_the_vault_untouched(client_and_vault):
    client, vault = client_and_vault()
    response = client.put(f"/api/secrets/{_SECRET_ID}", json={"description": "only metadata"})
    assert response.status_code == 400
    assert vault.store[uuid.UUID(_SECRET_ID)] == b"old-value"


def test_a_non_admin_cannot_delete_or_update_a_system_secret(client_and_vault):
    client, vault = client_and_vault(admin=False)
    assert client.delete(f"/api/secrets/{_SECRET_ID}").status_code == 403
    assert client.put(f"/api/secrets/{_SECRET_ID}", json={"value": "attacker"}).status_code == 403
    assert vault.store == {uuid.UUID(_SECRET_ID): b"old-value"}


def test_an_unknown_id_is_still_a_404(client_and_vault):
    client, _vault = client_and_vault()
    other = str(uuid.uuid4())
    with patch.object(secrets_module, "_get_connector_bridged_secret", AsyncMock(return_value=None)):
        assert client.delete(f"/api/secrets/{other}").status_code == 404
    assert client.put(f"/api/secrets/{other}", json={"value": "v"}).status_code == 404


def test_the_internal_key_cannot_rotate_or_delete_a_system_secret(client_and_vault, monkeypatch):
    """#17038: an automatic actor never destroys or rotates a SYSTEM credential."""
    client, vault = client_and_vault()
    monkeypatch.setattr(secrets_system_vault, "verify_internal_api_key", lambda key: key == "svc-key")
    headers = {"X-Internal-API-Key": "svc-key"}
    assert client.delete(f"/api/secrets/{_SECRET_ID}", headers=headers).status_code == 403
    assert client.put(f"/api/secrets/{_SECRET_ID}", json={"value": "x"}, headers=headers).status_code == 403
    assert vault.store == {uuid.UUID(_SECRET_ID): b"old-value"}
    # the same call from a human admin (no key) is unchanged
    assert client.delete(f"/api/secrets/{_SECRET_ID}").status_code == 200
    assert vault.store == {}


def test_a_non_uuid_caller_keeps_legacy_secrets_working(client_and_vault, monkeypatch):
    """The principal resolves only for an actual SYSTEM secret (non-UUID identities stay 404/legacy)."""
    client, _vault = client_and_vault()
    monkeypatch.setattr(secrets_system_vault, "_principal", AsyncMock(side_effect=ValueError("not a uuid")))
    legacy_only = str(uuid.uuid4())
    with patch.object(secrets_module, "_get_connector_bridged_secret", AsyncMock(return_value=None)):
        assert client.delete(f"/api/secrets/{legacy_only}").status_code == 404
    assert client.put(f"/api/secrets/{legacy_only}", json={"value": "v"}).status_code == 404
    secrets_system_vault._principal.assert_not_awaited()


@pytest.mark.parametrize(
    "handler, helper",
    [
        (secrets_module.create_secret, "_create_system_vault_secret"),
        (secrets_module.update_secret, "rotate_system_vault_secret"),
        (secrets_module.delete_secret, "delete_system_vault_secret"),
    ],
)
def test_every_write_handler_reaches_the_system_vault(handler, helper):
    """Guard: a write handler added or edited later cannot omit the vault destination (#17731)."""
    assert helper in inspect.getsource(handler)


class TestListIncludesSystemVaultMetadata:
    """GET / adds SYSTEM-vault metadata for admins only, never a value (#17099)."""

    def test_an_admin_sees_system_metadata_and_no_value(self, client_and_vault, monkeypatch):
        from services.secrets_principal_resolver import ADMIN_PERMISSION

        client, _vault = client_and_vault()
        monkeypatch.setattr(
            secrets_system_vault,
            "_principal",
            AsyncMock(return_value=(uuid.UUID(_ADMIN_ID), {ADMIN_PERMISSION})),
        )
        body = client.get("/api/secrets/").json()
        assert body["secrets"] == [{"id": "legacy-1", "name": "old"}]
        vault = body["system_vault"]
        assert vault["available"] is True
        assert [s["id"] for s in vault["secrets"]] == [_SECRET_ID]  # the user-vault row is excluded
        assert vault["secrets"][0]["name"] == "vault-key"
        assert "SEALED" not in client.get("/api/secrets/").text
        assert "old-value" not in client.get("/api/secrets/").text
        assert not {"value", "sealed_value"} & set(vault["secrets"][0])

    def test_a_non_admin_gets_exactly_the_legacy_response(self, client_and_vault):
        client, _vault = client_and_vault()  # _principal grants no permissions
        body = client.get("/api/secrets/").json()
        assert "system_vault" not in body
        assert body["secrets"] == [{"id": "legacy-1", "name": "old"}]

    def test_an_unavailable_vault_is_reported_not_omitted(self, client_and_vault, monkeypatch):
        from services.secrets_principal_resolver import ADMIN_PERMISSION

        client, _vault = client_and_vault()
        monkeypatch.setattr(
            secrets_system_vault,
            "_principal",
            AsyncMock(return_value=(uuid.UUID(_ADMIN_ID), {ADMIN_PERMISSION})),
        )
        monkeypatch.setattr(secrets_system_vault, "_coordinator_or_none", lambda: None)
        body = client.get("/api/secrets/").json()
        assert body["system_vault"] == {"available": False, "secrets": []}
        assert body["secrets"] == [{"id": "legacy-1", "name": "old"}]
