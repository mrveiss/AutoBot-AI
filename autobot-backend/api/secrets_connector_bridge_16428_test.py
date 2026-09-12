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
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas_system import ChatSecretScope
from autobot_shared.status_enums import SecretType


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
        store.store = AsyncMock(return_value=("secret-123", {}))
        request = _connector_secret_request(auth_type="BearerAuth", credentials={"token": "tok-abc"})

        with patch("api.secrets.get_credential_store", return_value=store):
            result = await _create_connector_bridged_secret(request, "owner-1")

        assert result["id"] == "secret-123"
        assert "value" not in result
        assert result["metadata"]["connector_id"] == "conn-1"
        store.store.assert_awaited_once_with("conn-1", "owner-1", BearerAuth, {"token": "tok-abc"})

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
        store.store = AsyncMock(return_value=("secret-456", {}))
        request = _connector_secret_request(
            type=SecretType.CONNECTOR_OAUTH_TOKEN, auth_type="OAuthRefreshAuth", credentials=oauth_creds
        )

        with patch("api.secrets.get_credential_store", return_value=store):
            result = await _create_connector_bridged_secret(request, "owner-1")

        assert result["id"] == "secret-456"
        store.store.assert_awaited_once_with("conn-1", "owner-1", OAuthRefreshAuth, oauth_creds)

    @pytest.mark.asyncio
    async def test_oauth_refresh_auth_missing_a_field_is_rejected(self):
        from api.secrets import _create_connector_bridged_secret

        request = _connector_secret_request(
            auth_type="OAuthRefreshAuth",
            credentials={"client_id": "cid"},  # missing client_secret, refresh_token, token_url
        )
        with pytest.raises(ValueError, match="missing required auth field"):
            await _create_connector_bridged_secret(request, "owner-1")


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
