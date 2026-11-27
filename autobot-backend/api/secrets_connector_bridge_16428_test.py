# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Connector credential templates write where knowledge connectors read (#16428).

A connector credential template on the Secrets page (``POST /api/secrets``)
used to save into the page's own file store, a separate write path from
``ConnectorCredentialStore`` (ADR-007), which is what knowledge connectors
actually read from -- so a template never configured a connector.

Owner decision, via #13632's ruling (one provider definition, credentials in
one store, ``ConnectorCredentialStore``): a request naming ``connector_id``
and ``auth_type`` bridges transparently to it for create/get/rotate/revoke,
instead of the legacy file. These prove the bridge for both auth shapes AC3
names explicitly: a single-field kind (``BearerAuth``) and the multi-field
kind (``OAuthRefreshAuth``, four fields bundled together).

#22234: the ``OAuthRefreshAuth`` bridge stores the refreshable bundle
(``client_id`` and ``token_url`` included), so the credential survives its
first access-token expiry instead of dying in ``_resolve_app_credentials``.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas_system import ChatSecretScope
from autobot_shared.status_enums import SecretType


@pytest.fixture(autouse=True)
def committed_audit():
    """The canonical audit store commits the required before-write record (#20557).

    A unit test has no ``audit_logs`` database; the 503 a failed record gives is proven
    in ``secrets_defects_20557_test.py`` and against Postgres in ``tests/migrations``.
    """
    with patch("services.audit.audit.record_committed", AsyncMock(return_value=True)) as recorded:
        yield recorded


def _connector_secret_request(**overrides):
    from api.schemas_system import SecretCreateRequest

    fields = {
        "name": "my-connector-cred",
        "type": SecretType.API_KEY,
        "scope": ChatSecretScope.USER,
        "connector_id": "conn-1",
        "auth_type": "BearerAuth",
        "credentials": {"token": "tok-abc"},
    }
    fields.update(overrides)
    return SecretCreateRequest(**fields)


class TestConnectorBridgedSecretCreate:
    """``_create_connector_bridged_secret`` / ``create_secret``'s #16428 branch."""

    @pytest.mark.asyncio
    async def test_unknown_auth_type_is_rejected(self):
        from api.secrets import _create_connector_bridged_secret

        request = _connector_secret_request(auth_type="NotARealAuthType")
        with pytest.raises(ValueError, match="unknown auth_type"):
            await _create_connector_bridged_secret(request, "owner-1")

    @pytest.mark.asyncio
    async def test_missing_required_field_is_rejected(self):
        from api.secrets import _create_connector_bridged_secret

        request = _connector_secret_request(auth_type="BearerAuth", credentials={})
        with pytest.raises(ValueError, match="missing required auth field"):
            await _create_connector_bridged_secret(request, "owner-1")

    @pytest.mark.asyncio
    async def test_bearer_auth_stores_through_credential_store_and_returns_no_value(self):
        from api.secrets import _create_connector_bridged_secret
        from autobot_shared.auth.connector_auth import BearerAuth

        store = MagicMock()
        store.store_bridged = AsyncMock(return_value="secret-123")
        request = _connector_secret_request(auth_type="BearerAuth", credentials={"token": "tok-abc"})

        with patch("api.secrets.get_credential_store", return_value=store):
            result = await _create_connector_bridged_secret(request, "owner-1")

        assert result["id"] == "secret-123"
        assert "value" not in result
        assert result["metadata"]["connector_id"] == "conn-1"
        store.store_bridged.assert_awaited_once_with("conn-1", "owner-1", BearerAuth, {"token": "tok-abc"})

    @pytest.mark.asyncio
    async def test_oauth_refresh_auth_stores_the_full_multi_field_bundle(self):
        """The multi-field kind AC3 names, not just the single-field one above."""
        from api.secrets import _create_connector_bridged_secret
        from autobot_shared.auth.connector_auth import OAuthRefreshAuth

        oauth_creds = {
            "client_id": "cid",
            "client_secret": "csecret",  # pragma: allowlist secret
            "refresh_token": "rtok",
            "token_url": "https://provider.example/token",
        }
        store = MagicMock()
        store.store_bridged = AsyncMock(return_value="secret-456")
        request = _connector_secret_request(
            type=SecretType.CONNECTOR_OAUTH_TOKEN, auth_type="OAuthRefreshAuth", credentials=oauth_creds
        )

        with patch("api.secrets.get_credential_store", return_value=store):
            result = await _create_connector_bridged_secret(request, "owner-1")

        assert result["id"] == "secret-456"
        store.store_bridged.assert_awaited_once_with("conn-1", "owner-1", OAuthRefreshAuth, oauth_creds)

    @pytest.mark.asyncio
    async def test_oauth_refresh_auth_missing_a_field_is_rejected(self):
        from api.secrets import _create_connector_bridged_secret

        request = _connector_secret_request(
            auth_type="OAuthRefreshAuth",
            credentials={"client_id": "cid"},  # missing client_secret, refresh_token, token_url
        )
        with pytest.raises(ValueError, match="missing required auth field"):
            await _create_connector_bridged_secret(request, "owner-1")


_OAUTH_CREDS = {
    "client_id": "cid",
    "client_secret": "csecret",  # pragma: allowlist secret
    "refresh_token": "rtok",
    "token_url": "https://provider.example/token",
}


def _dict_backed_store():
    """A real ConnectorCredentialStore over a dict-backed fake SecretsService."""
    from knowledge.connectors.credential_store import ConnectorCredentialStore

    rows = {}
    svc = MagicMock()

    def _create(name, secret_type, value, scope, created_by=None, **_):
        rows[f"sid-{name}"] = {"id": f"sid-{name}", "value": value, "created_by": created_by}
        return {"id": f"sid-{name}"}

    def _get(secret_id=None, include_value=False, **_):
        return dict(rows[secret_id]) if secret_id in rows else None

    def _update(secret_id, value=None, **_):
        rows[secret_id]["value"] = value
        return True

    svc.create_secret.side_effect = _create
    svc.get_secret.side_effect = _get
    svc.update_secret.side_effect = _update
    store = ConnectorCredentialStore(svc)
    store.rows = rows
    return store


@pytest.fixture
def route_client(monkeypatch):
    """The real secrets router over HTTP: admin dep overridden, everything else real.

    The credential store is real over a dict-backed service; DNS and the token
    endpoint are stubbed so no test touches the network.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api import secrets as secrets_module
    from auth_middleware import check_admin_permission
    from autobot_shared.leader_lease import LeaderLease
    from knowledge.connectors import oauth_bundle
    from knowledge.connectors.credential_store import ConnectorCredentialStore

    app = FastAPI()
    app.include_router(secrets_module.router, prefix="/api/secrets")
    app.dependency_overrides[check_admin_permission] = lambda: True
    auth = MagicMock()
    auth.get_user_from_request.return_value = {"user_id": "owner-1"}
    store = _dict_backed_store()
    monkeypatch.setattr(oauth_bundle, "resolve_safe_ip", AsyncMock(return_value="203.0.113.7"))
    monkeypatch.setattr(oauth_bundle, "pinned_connector", AsyncMock(return_value="PINNED"))
    monkeypatch.setattr(LeaderLease, "update_leadership", AsyncMock(return_value=False))
    monkeypatch.setattr(ConnectorCredentialStore, "_refresh_lock_available", AsyncMock(return_value=False))
    with (
        patch("api.secrets.check_rate_limit", AsyncMock(return_value=None)),
        patch("api.secrets_audit.get_auth_middleware", return_value=auth),
        patch("api.secrets.get_auth_middleware", return_value=auth),
        patch("api.secrets.audit_record", MagicMock()),
        patch("api.secrets.audit_secret_op", AsyncMock(return_value=None)),
        patch("api.secrets.get_credential_store", return_value=store),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        client.store = store
        yield client


def _post_oauth(client, **overrides):
    creds = {**_OAUTH_CREDS, **overrides}
    creds = {k: v for k, v in creds.items() if v is not None}
    body = {
        "name": "oauth-cred",
        "type": "connector_oauth_token",
        "scope": "user",
        "connector_id": "conn-1",
        "auth_type": "OAuthRefreshAuth",
        "credentials": creds,
    }
    return client.post("/api/secrets/", json=body)


class TestBridgedOAuthCredentialRefreshes:
    """#22234: a Secrets-page OAuthRefreshAuth credential survives its first expiry."""

    def test_created_credential_refreshes_after_forced_expiry_through_a_pinned_connector(
        self, route_client, monkeypatch
    ):
        from datetime import datetime, timedelta, timezone

        from knowledge.connectors import oauth_bundle, oauth_flow

        calls = []

        async def _fake_refresh(token_url, client_id, client_secret, refresh_token, **kw):
            calls.append((token_url, client_id, client_secret, refresh_token, kw.get("connector")))
            return {"access_token": "fresh", "expires_in": 3600}

        monkeypatch.setattr(oauth_flow, "refresh_access_token", _fake_refresh)
        response = _post_oauth(route_client)
        assert response.status_code == 201
        store = route_client.store
        row = store.rows[response.json()["secret"]["id"]]
        bundle = json.loads(row["value"])
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        row["value"] = json.dumps({**bundle, "access_token": "stale", "access_token_expires_at": past})

        token = asyncio.run(store.get_access_token(row["id"], "owner-1"))

        assert token == "fresh"
        assert calls == [("https://provider.example/token", "cid", "csecret", "rtok", "PINNED")]
        oauth_bundle.pinned_connector.assert_awaited_once_with(_OAUTH_CREDS["token_url"])

    @pytest.mark.parametrize("field", ["token_url", "client_id"])
    def test_missing_or_empty_field_is_a_400_at_create_and_nothing_is_stored(self, route_client, field):
        for value in (None, ""):
            assert _post_oauth(route_client, **{field: value}).status_code == 400
        route_client.store._svc.create_secret.assert_not_called()

    @pytest.mark.parametrize(
        "url", ["http://provider.example/token", "https://127.0.0.1/token", "https://169.254.169.254/latest"]
    )
    def test_unsafe_token_url_is_a_400_at_create(self, route_client, monkeypatch, url):
        monkeypatch.undo()  # real resolve_safe_ip: loopback / metadata literals must be refused
        assert _post_oauth(route_client, token_url=url).status_code == 400
        route_client.store._svc.create_secret.assert_not_called()

    def test_scopes_must_be_a_list_of_strings(self, route_client):
        assert _post_oauth(route_client, scopes="a b").status_code == 400

    def test_legacy_private_token_url_is_refused_at_refresh_before_any_post(self, route_client, monkeypatch):
        from autobot_shared.security.ssrf_guard import SSRFError
        from knowledge.connectors import oauth_bundle, oauth_flow

        reached = AsyncMock()
        monkeypatch.setattr(oauth_flow, "refresh_access_token", reached)
        monkeypatch.setattr(oauth_bundle, "pinned_connector", AsyncMock(side_effect=SSRFError("private")))
        legacy = {
            **_OAUTH_CREDS,
            "token_url": "https://127.0.0.1/token",
            "access_token": "",
            "access_token_expires_at": None,
        }
        route_client.store.rows["legacy"] = {"id": "legacy", "value": json.dumps(legacy), "created_by": "owner-1"}

        with pytest.raises(SSRFError):
            asyncio.run(route_client.store.get_access_token("legacy", "owner-1"))
        reached.assert_not_awaited()

    def test_rotate_refuses_a_non_string_token_url(self, route_client):
        secret_id = _post_oauth(route_client).json()["secret"]["id"]
        with pytest.raises(ValueError):
            asyncio.run(route_client.store.rotate(secret_id, {"token_url": 123}, "owner-1"))

    def test_rotate_refuses_an_unsafe_token_url(self, route_client):
        secret_id = _post_oauth(route_client).json()["secret"]["id"]
        with patch("knowledge.connectors.oauth_bundle.resolve_safe_ip", side_effect=ValueError("private")):
            with pytest.raises(ValueError):
                asyncio.run(route_client.store.rotate(secret_id, {"token_url": "https://10.0.0.5/t"}, "owner-1"))
        with pytest.raises(ValueError):
            asyncio.run(route_client.store.rotate(secret_id, {"token_url": "http://x.example/t"}, "owner-1"))


class TestGetConnectorBridgedSecretEnforcesOwnership:
    """``_get_connector_bridged_secret`` must refuse another owner's metadata.

    It reads straight through ``SecretsService.get_secret``, which has no
    per-user check of its own -- ``ConnectorCredentialStore.load``/``rotate``/
    ``revoke`` are the only reason this secret was ever owner-scoped at all,
    and this dual-read bypassed that entirely. Reuses
    ``ConnectorCredentialStore._require_owner`` rather than a second copy of
    the same check, so the boundary can't drift between the two paths.
    """

    @pytest.mark.asyncio
    async def test_returns_metadata_for_the_owner(self):
        from api.secrets import _get_connector_bridged_secret

        bridged = {
            "id": "secret-1",
            "secret_type": "connector_api_key",  # pragma: allowlist secret
            "scope": "user",
            "created_by": "owner-1",
        }
        connector_svc = MagicMock()
        connector_svc.get_secret = MagicMock(return_value=bridged)

        with patch("api.secrets.get_secrets_service", return_value=connector_svc):
            result = await _get_connector_bridged_secret("secret-1", "owner-1")

        assert result["id"] == "secret-1"

    @pytest.mark.asyncio
    async def test_refuses_a_different_owner(self):
        from api.secrets import _get_connector_bridged_secret

        bridged = {
            "id": "secret-1",
            "secret_type": "connector_api_key",  # pragma: allowlist secret
            "scope": "user",
            "created_by": "owner-1",
        }
        connector_svc = MagicMock()
        connector_svc.get_secret = MagicMock(return_value=bridged)

        with patch("api.secrets.get_secrets_service", return_value=connector_svc):
            with pytest.raises(PermissionError):
                await _get_connector_bridged_secret("secret-1", "owner-2")


class TestCreateSecretEndpointRoutesToTheBridge:
    """``POST /api/secrets`` sends a connector-bridged request to the new
    path and a plain one to the legacy store, unchanged."""

    @pytest.mark.asyncio
    async def test_connector_id_present_never_touches_the_legacy_store(self):
        from api.secrets import create_secret

        store = MagicMock()
        store.store = AsyncMock(return_value=("secret-789", {}))
        request = _connector_secret_request()
        http_request = MagicMock()
        http_request.client.host = "127.0.0.1"

        with (
            patch("api.secrets.get_credential_store", return_value=store),
            patch("api.secrets.secrets_manager") as legacy,
            patch("api.secrets.get_auth_middleware") as auth_mw,
        ):
            auth_mw.return_value.get_user_from_request.return_value = {"user_id": "owner-1"}
            response = await create_secret(request=request, http_request=http_request, admin_check=True)

        legacy.create_secret.assert_not_called()
        assert response.status_code == 201
        body = json.loads(response.body)
        assert body["secret"]["id"] == "secret-789"
        assert "value" not in body["secret"]


class TestUpdateSecretRotatesTheBridgedCredential:
    """``PUT /api/secrets/{id}`` rotates a bridged secret instead of 404ing
    once the legacy store reports it doesn't own that id."""

    @pytest.mark.asyncio
    async def test_rotates_when_not_a_legacy_secret_and_credentials_given(self):
        from api.schemas_system import SecretUpdateRequest
        from api.secrets import update_secret

        store = MagicMock()
        store.rotate = AsyncMock(return_value=None)
        bridged_after = {
            "id": "secret-1",
            "secret_type": "connector_api_key",  # pragma: allowlist secret
            "scope": "user",
            "created_by": "owner-1",
        }
        connector_svc = MagicMock()
        connector_svc.get_secret = MagicMock(return_value=bridged_after)
        request = SecretUpdateRequest(credentials={"token": "new-tok"})
        http_request = MagicMock()
        http_request.client.host = "127.0.0.1"

        with (
            patch("api.secrets.secrets_manager") as legacy,
            patch("api.secrets.get_credential_store", return_value=store),
            patch("api.secrets.get_secrets_service", return_value=connector_svc),
            patch("api.secrets.get_auth_middleware") as auth_mw,
        ):
            legacy.update_secret = MagicMock(return_value=None)
            auth_mw.return_value.get_user_from_request.return_value = {"user_id": "owner-1"}
            response = await update_secret(
                secret_id="secret-1", request=request, http_request=http_request, admin_check=True
            )

        store.rotate.assert_awaited_once_with("secret-1", {"token": "new-tok"}, "owner-1")
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["secret"]["id"] == "secret-1"
        assert "value" not in body["secret"]

    @pytest.mark.asyncio
    async def test_404s_when_not_in_either_store(self):
        from fastapi import HTTPException

        from api.schemas_system import SecretUpdateRequest
        from api.secrets import update_secret

        store = MagicMock()
        store.rotate = AsyncMock(side_effect=LookupError("not found"))
        request = SecretUpdateRequest(credentials={"token": "new-tok"})
        http_request = MagicMock()
        http_request.client.host = "127.0.0.1"

        with (
            patch("api.secrets.secrets_manager") as legacy,
            patch("api.secrets.get_credential_store", return_value=store),
            patch("api.secrets.get_auth_middleware") as auth_mw,
        ):
            legacy.update_secret = MagicMock(return_value=None)
            auth_mw.return_value.get_user_from_request.return_value = {"user_id": "owner-1"}
            with pytest.raises(HTTPException) as exc_info:
                await update_secret(secret_id="ghost", request=request, http_request=http_request, admin_check=True)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_404s_when_no_credentials_and_not_a_legacy_secret(self):
        """A plain metadata-only update (no credentials) on an id neither
        store recognises must still 404 -- it must not silently no-op."""
        from fastapi import HTTPException

        from api.schemas_system import SecretUpdateRequest
        from api.secrets import update_secret

        request = SecretUpdateRequest(description="new description")
        http_request = MagicMock()
        http_request.client.host = "127.0.0.1"

        with patch("api.secrets.secrets_manager") as legacy:
            legacy.update_secret = MagicMock(return_value=None)
            with pytest.raises(HTTPException) as exc_info:
                await update_secret(secret_id="ghost", request=request, http_request=http_request, admin_check=True)

        assert exc_info.value.status_code == 404


class TestDeleteSecretRevokesTheBridgedCredential:
    """``DELETE /api/secrets/{id}`` revokes a bridged secret instead of 404ing
    once the legacy store reports it doesn't own that id."""

    @pytest.mark.asyncio
    async def test_revokes_when_not_a_legacy_secret_but_bridged(self):
        from api.secrets import delete_secret

        store = MagicMock()
        store.revoke = AsyncMock(return_value=None)
        bridged = {
            "id": "secret-1",
            "secret_type": "connector_api_key",  # pragma: allowlist secret
            "scope": "user",
            "created_by": "owner-1",
        }
        connector_svc = MagicMock()
        connector_svc.get_secret = MagicMock(return_value=bridged)
        http_request = MagicMock()
        http_request.client.host = "127.0.0.1"

        with (
            patch("api.secrets.secrets_manager") as legacy,
            patch("api.secrets.get_credential_store", return_value=store),
            patch("api.secrets.get_secrets_service", return_value=connector_svc),
            patch("api.secrets.get_auth_middleware") as auth_mw,
        ):
            legacy.delete_secret = MagicMock(return_value=False)
            auth_mw.return_value.get_user_from_request.return_value = {"user_id": "owner-1"}
            response = await delete_secret(secret_id="secret-1", http_request=http_request, admin_check=True)

        store.revoke.assert_awaited_once_with("secret-1", "owner-1")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_404s_when_not_in_either_store(self):
        from fastapi import HTTPException

        from api.secrets import delete_secret

        connector_svc = MagicMock()
        connector_svc.get_secret = MagicMock(return_value=None)
        http_request = MagicMock()
        http_request.client.host = "127.0.0.1"

        with (
            patch("api.secrets.secrets_manager") as legacy,
            patch("api.secrets.get_secrets_service", return_value=connector_svc),
            patch("api.secrets.get_auth_middleware") as auth_mw,
        ):
            legacy.delete_secret = MagicMock(return_value=False)
            auth_mw.return_value.get_user_from_request.return_value = {"user_id": "owner-1"}
            with pytest.raises(HTTPException) as exc_info:
                await delete_secret(secret_id="ghost", http_request=http_request, admin_check=True)

        assert exc_info.value.status_code == 404
