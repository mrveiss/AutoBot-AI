# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit and integration tests for ConnectorCredentialStore (ADR-007 / GH#9019)."""

import json
from unittest.mock import MagicMock

import pytest

from autobot_shared.auth.connector_auth import (
    ApiKeyAuth,
    BasicAuth,
    BearerAuth,
    OAuthRefreshAuth,
)
from knowledge.connectors.credential_store import ConnectorCredentialStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_svc(*, existing_secret=None):
    """Return a mock SecretsService."""
    svc = MagicMock()
    creds_store = {}

    def _create(name, secret_type, value, scope, created_by=None, **_):
        sid = f"sid-{name}"
        creds_store[sid] = {"id": sid, "name": name, "value": value, "created_by": created_by}
        return {"id": sid}

    def _get(secret_id=None, name=None, include_value=False, accessed_by=None, **_):
        secret = creds_store.get(secret_id)
        if secret is None:
            return None
        out = dict(secret)
        if not include_value:
            out.pop("value", None)
        return out

    def _update(secret_id, value=None, updated_by=None, **_):
        if secret_id not in creds_store:
            return False
        if value is not None:
            creds_store[secret_id]["value"] = value
        return True

    def _delete(secret_id, deleted_by=None, **_):
        return creds_store.pop(secret_id, None) is not None

    svc.create_secret.side_effect = _create
    svc.get_secret.side_effect = _get
    svc.update_secret.side_effect = _update
    svc.delete_secret.side_effect = _delete
    return svc, creds_store


# ---------------------------------------------------------------------------
# __sensitive_fields__ on auth dataclasses
# ---------------------------------------------------------------------------


def test_bearer_auth_sensitive_fields():
    assert BearerAuth.__sensitive_fields__ == frozenset({"token"})


def test_api_key_auth_sensitive_fields():
    assert ApiKeyAuth.__sensitive_fields__ == frozenset({"key"})


def test_basic_auth_sensitive_fields():
    assert BasicAuth.__sensitive_fields__ == frozenset({"password"})


def test_oauth_refresh_auth_sensitive_fields():
    assert OAuthRefreshAuth.__sensitive_fields__ == frozenset({"client_secret", "refresh_token"})


# ---------------------------------------------------------------------------
# ConnectorCredentialStore.store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_extracts_sensitive_fields():
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)

    config = {
        "client_id": "abc",
        "client_secret": "s3cr3t",
        "refresh_token": "tok",
        "token_url": "https://example.com/token",
        "scopes": ["read"],
    }
    secret_id, sanitized = await cs.store("conn-1", "user-1", OAuthRefreshAuth, config)

    assert secret_id == "sid-connector:conn-1:auth"
    assert "client_secret" not in sanitized
    assert "refresh_token" not in sanitized
    assert sanitized["client_id"] == "abc"
    assert sanitized["token_url"] == "https://example.com/token"

    # Stored secret must contain the sensitive values.
    stored = store[secret_id]["value"]
    creds = json.loads(stored)
    assert creds["client_secret"] == "s3cr3t"
    assert creds["refresh_token"] == "tok"


@pytest.mark.asyncio
async def test_store_bearer_auth():
    svc, _ = _make_svc()
    cs = ConnectorCredentialStore(svc)

    secret_id, sanitized = await cs.store("conn-2", "user-1", BearerAuth, {"token": "t0k3n"})
    assert "token" not in sanitized
    assert secret_id


@pytest.mark.asyncio
async def test_store_raises_when_no_sensitive_fields():
    class NoSensitive:
        pass

    svc, _ = _make_svc()
    cs = ConnectorCredentialStore(svc)
    with pytest.raises(ValueError, match="__sensitive_fields__"):
        await cs.store("c", "u", NoSensitive, {})


# ---------------------------------------------------------------------------
# ConnectorCredentialStore.load
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_merges_credentials():
    svc, _ = _make_svc()
    cs = ConnectorCredentialStore(svc)

    config = {"client_id": "abc", "client_secret": "s3cr3t", "refresh_token": "tok", "token_url": "x"}
    secret_id, sanitized = await cs.store("conn-3", "user-1", OAuthRefreshAuth, config)

    full = await cs.load(secret_id, sanitized, OAuthRefreshAuth, "user-1")
    assert full["client_secret"] == "s3cr3t"
    assert full["refresh_token"] == "tok"
    assert full["client_id"] == "abc"


@pytest.mark.asyncio
async def test_load_raises_lookup_error_when_missing():
    svc, _ = _make_svc()
    cs = ConnectorCredentialStore(svc)
    with pytest.raises(LookupError):
        await cs.load("nonexistent", {}, OAuthRefreshAuth, "user-1")


@pytest.mark.asyncio
async def test_load_raises_permission_error_on_owner_mismatch():
    svc, _ = _make_svc()
    cs = ConnectorCredentialStore(svc)

    config = {"token": "tok"}
    secret_id, _ = await cs.store("conn-4", "user-1", BearerAuth, config)

    with pytest.raises(PermissionError):
        await cs.load(secret_id, {}, BearerAuth, "user-WRONG")


# ---------------------------------------------------------------------------
# ConnectorCredentialStore.rotate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rotate_updates_credentials():
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)

    config = {"client_id": "abc", "client_secret": "old", "refresh_token": "old_tok", "token_url": "x"}
    secret_id, sanitized = await cs.store("conn-5", "user-1", OAuthRefreshAuth, config)

    await cs.rotate(secret_id, {"refresh_token": "new_tok"}, "user-1")

    stored = json.loads(store[secret_id]["value"])
    assert stored["refresh_token"] == "new_tok"
    assert stored["client_secret"] == "old"


@pytest.mark.asyncio
async def test_rotate_raises_lookup_error_when_missing():
    svc, _ = _make_svc()
    cs = ConnectorCredentialStore(svc)
    with pytest.raises(LookupError):
        await cs.rotate("nonexistent", {"token": "x"}, "user-1")


# ---------------------------------------------------------------------------
# ConnectorCredentialStore.revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_deletes_secret():
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)

    config = {"token": "tok"}
    secret_id, _ = await cs.store("conn-6", "user-1", BearerAuth, config)
    assert secret_id in store

    await cs.revoke(secret_id, "user-1")
    assert secret_id not in store


# ---------------------------------------------------------------------------
# Round-trip integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_round_trip_store_load_rotate_revoke():
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)

    original = {
        "client_id": "cid",
        "client_secret": "cs1",
        "refresh_token": "rt1",
        "token_url": "https://example.com/token",
        "scopes": ["read"],
    }
    secret_id, sanitized = await cs.store("round-trip", "owner-1", OAuthRefreshAuth, original)

    # load round-trip
    full = await cs.load(secret_id, sanitized, OAuthRefreshAuth, "owner-1")
    assert full["client_secret"] == "cs1"
    assert full["refresh_token"] == "rt1"

    # rotate
    await cs.rotate(secret_id, {"refresh_token": "rt2", "client_secret": "cs2"}, "owner-1")
    full2 = await cs.load(secret_id, sanitized, OAuthRefreshAuth, "owner-1")
    assert full2["refresh_token"] == "rt2"
    assert full2["client_secret"] == "cs2"

    # revoke
    await cs.revoke(secret_id, "owner-1")
    assert secret_id not in store


# ---------------------------------------------------------------------------
# OAuth auth-code tokens: store_oauth + get_access_token auto-refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_oauth_persists_bundle_and_credentials_isolated():
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)

    secret_id = await cs.store_oauth(
        connector_id="gdrive-1",
        owner_id="user-9",
        provider="google",
        token_response={"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
        client_id="cid",
        client_secret="csec",
        token_url="https://oauth2.googleapis.com/token",
        scopes=["drive.readonly"],
    )
    bundle = json.loads(store[secret_id]["value"])
    assert bundle["access_token"] == "at"
    assert bundle["refresh_token"] == "rt"
    assert bundle["client_secret"] == "csec"
    assert bundle["access_token_expires_at"] is not None
    assert store[secret_id]["created_by"] == "user-9"


@pytest.mark.asyncio
async def test_get_access_token_returns_unexpired_without_refresh(monkeypatch):
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await cs.store_oauth(
        "c1",
        "u1",
        "google",
        {"access_token": "still-good", "refresh_token": "rt", "expires_in": 3600},
        "cid",
        "csec",
        "https://token",
        ["s"],
    )

    # refresh_access_token must NOT be called for a valid token.
    from knowledge.connectors import oauth_flow

    async def _boom(*a, **k):
        raise AssertionError("refresh should not be called")

    monkeypatch.setattr(oauth_flow, "refresh_access_token", _boom)
    token = await cs.get_access_token(secret_id, "u1")
    assert token == "still-good"


@pytest.mark.asyncio
async def test_get_access_token_refreshes_when_expired(monkeypatch):
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    # expires_in=0 → immediately within the skew window → expired.
    secret_id = await cs.store_oauth(
        "c2",
        "u1",
        "gitlab",
        {"access_token": "old", "refresh_token": "rt-old", "expires_in": 0},
        "cid",
        "csec",
        "https://token",
        ["s"],
    )

    from knowledge.connectors import oauth_flow

    async def _fake_refresh(token_url, client_id, client_secret, refresh_token):
        assert refresh_token == "rt-old"
        return {"access_token": "new", "refresh_token": "rt-new", "expires_in": 3600}

    monkeypatch.setattr(oauth_flow, "refresh_access_token", _fake_refresh)
    token = await cs.get_access_token(secret_id, "u1")
    assert token == "new"

    # Secret rotated in place: new access + rotated refresh token persisted.
    bundle = json.loads(store[secret_id]["value"])
    assert bundle["access_token"] == "new"
    assert bundle["refresh_token"] == "rt-new"


@pytest.mark.asyncio
async def test_get_access_token_owner_mismatch_raises():
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await cs.store_oauth(
        "c3",
        "owner-a",
        "google",
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
        "cid",
        "csec",
        "https://token",
        ["s"],
    )
    with pytest.raises(PermissionError):
        await cs.get_access_token(secret_id, "intruder")


@pytest.mark.asyncio
async def test_get_access_token_missing_secret_raises():
    svc, _ = _make_svc()
    cs = ConnectorCredentialStore(svc)
    with pytest.raises(LookupError):
        await cs.get_access_token("nope", "u1")


@pytest.mark.asyncio
async def test_get_access_token_expired_without_refresh_token_raises(monkeypatch):
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await cs.store_oauth(
        "c4",
        "u1",
        "google",
        {"access_token": "old", "expires_in": 0},  # no refresh_token
        "cid",
        "csec",
        "https://token",
        ["s"],
    )
    with pytest.raises(LookupError, match="re-auth required"):
        await cs.get_access_token(secret_id, "u1")
