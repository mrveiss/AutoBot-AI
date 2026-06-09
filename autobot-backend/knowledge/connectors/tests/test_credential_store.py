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
