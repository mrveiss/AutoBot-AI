# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit and integration tests for ConnectorCredentialStore (ADR-007 / GH#9019)."""

import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.auth.connector_auth import (
    ApiKeyAuth,
    BasicAuth,
    BearerAuth,
    OAuthRefreshAuth,
)
from autobot_shared.leader_lease import LeaderLease
from autobot_shared.time_utils import now_utc, parse_utc_iso
import knowledge.connectors.credential_store as mod
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
async def test_refresh_without_expires_in_reuses_the_reported_lifetime(monkeypatch):
    """#13626: a refresh response omitting ``expires_in`` must not clear the expiry.

    ``expires_in`` is RECOMMENDED, not REQUIRED, on a refresh response
    (RFC 6749 5.1). Writing None through set the expiry to "never", and a
    missing expiry is treated as non-expiring — so the credential was never
    refreshed again, the token lapsed server-side, and every later sync failed
    with a 401 hours or days after the refresh that caused it.
    """
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await cs.store_oauth(
        "c-13626",
        "u1",
        "gitlab",
        {"access_token": "old", "refresh_token": "rt-old", "expires_in": 0},
        "cid",
        "csec",
        "https://token",
        ["s"],
    )
    # The initial exchange reported a lifetime, so it is on the bundle.
    assert json.loads(store[secret_id]["value"])["access_token_lifetime_seconds"] == 0

    # Re-store with a real lifetime, then expire it, to model a live credential.
    secret_id = await cs.store_oauth(
        "c-13626b",
        "u1",
        "gitlab",
        {"access_token": "old", "refresh_token": "rt-old", "expires_in": 3600},
        "cid",
        "csec",
        "https://token",
        ["s"],
    )
    bundle = json.loads(store[secret_id]["value"])
    assert bundle["access_token_lifetime_seconds"] == 3600
    bundle["access_token_expires_at"] = (now_utc() - timedelta(seconds=1)).isoformat()
    store[secret_id]["value"] = json.dumps(bundle)

    from knowledge.connectors import oauth_flow

    async def _refresh_without_expiry(token_url, client_id, client_secret, refresh_token):
        return {"access_token": "new"}  # no expires_in — the provider omitted it

    monkeypatch.setattr(oauth_flow, "refresh_access_token", _refresh_without_expiry)
    assert await cs.get_access_token(secret_id, "u1") == "new"

    refreshed = json.loads(store[secret_id]["value"])
    assert refreshed["access_token_expires_at"] is not None, "expiry was cleared — refresh is now disabled forever"
    # Recomputed from the stored lifetime, so roughly an hour out, not in the past.
    expires_at = parse_utc_iso(refreshed["access_token_expires_at"])
    assert expires_at > now_utc() + timedelta(seconds=3000)


@pytest.mark.asyncio
async def test_refresh_without_expires_in_does_not_refresh_again_next_call(monkeypatch):
    """#13626: guards the naive fix of carrying the old timestamp forward.

    A refresh only runs once ``access_token_expires_at`` is already past, so
    reusing that timestamp would leave the credential looking expired and
    trigger a refresh on every single call.
    """
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await cs.store_oauth(
        "c-13626c",
        "u1",
        "gitlab",
        {"access_token": "old", "refresh_token": "rt-old", "expires_in": 3600},
        "cid",
        "csec",
        "https://token",
        ["s"],
    )
    bundle = json.loads(store[secret_id]["value"])
    bundle["access_token_expires_at"] = (now_utc() - timedelta(seconds=1)).isoformat()
    store[secret_id]["value"] = json.dumps(bundle)

    from knowledge.connectors import oauth_flow

    calls = []

    async def _refresh_without_expiry(token_url, client_id, client_secret, refresh_token):
        calls.append(refresh_token)
        return {"access_token": "new"}

    monkeypatch.setattr(oauth_flow, "refresh_access_token", _refresh_without_expiry)
    await cs.get_access_token(secret_id, "u1")
    await cs.get_access_token(secret_id, "u1")
    await cs.get_access_token(secret_id, "u1")

    assert len(calls) == 1, f"refreshed on every call — {len(calls)} refreshes for 3 reads"


@pytest.mark.asyncio
async def test_provider_that_never_reports_expiry_stays_non_expiring(monkeypatch):
    """#13626: only the lost-after-refresh case is a bug.

    A provider that never reports ``expires_in`` legitimately means
    non-expiring, and must not start refreshing on every call.
    """
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await cs.store_oauth(
        "c-13626d",
        "u1",
        "gitlab",
        {"access_token": "tok", "refresh_token": "rt"},  # no expires_in, ever
        "cid",
        "csec",
        "https://token",
        ["s"],
    )
    bundle = json.loads(store[secret_id]["value"])
    assert bundle["access_token_expires_at"] is None
    assert bundle["access_token_lifetime_seconds"] is None

    from knowledge.connectors import oauth_flow

    async def _boom(*_a, **_kw):
        raise AssertionError("must not refresh a credential the provider never gave an expiry for")

    monkeypatch.setattr(oauth_flow, "refresh_access_token", _boom)
    assert await cs.get_access_token(secret_id, "u1") == "tok"


@pytest.mark.asyncio
async def test_legacy_bundle_without_stored_lifetime_self_heals(monkeypatch):
    """#13626: credentials stored before this change carry no lifetime.

    They cannot be rescued on a refresh that also omits ``expires_in`` — nothing
    knows the lifetime — so that case must simply not regress. The first refresh
    that *does* report one backfills it, and the credential is fixed from then on.
    """
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await cs.store_oauth(
        "c-13626e",
        "u1",
        "gitlab",
        {"access_token": "old", "refresh_token": "rt", "expires_in": 3600},
        "cid",
        "csec",
        "https://token",
        ["s"],
    )
    # Model a pre-existing bundle: expiry present, lifetime key absent entirely.
    bundle = json.loads(store[secret_id]["value"])
    del bundle["access_token_lifetime_seconds"]
    bundle["access_token_expires_at"] = (now_utc() - timedelta(seconds=1)).isoformat()
    store[secret_id]["value"] = json.dumps(bundle)

    from knowledge.connectors import oauth_flow

    async def _refresh_reporting_expiry(token_url, client_id, client_secret, refresh_token):
        return {"access_token": "new", "expires_in": 7200}

    monkeypatch.setattr(oauth_flow, "refresh_access_token", _refresh_reporting_expiry)
    assert await cs.get_access_token(secret_id, "u1") == "new"

    healed = json.loads(store[secret_id]["value"])
    assert healed["access_token_lifetime_seconds"] == 7200, "lifetime not backfilled on a reporting refresh"
    assert healed["access_token_expires_at"] is not None


@pytest.mark.parametrize("bad_expires_in", ["", "n/a", "3600s", [], {}])
@pytest.mark.asyncio
async def test_malformed_expires_in_falls_back_and_keeps_the_stored_lifetime(bad_expires_in, monkeypatch):
    """#13626: an unusable ``expires_in`` must behave exactly like an absent one.

    Guarding on the raw value let these through the "provider reported one" test
    while still deriving None, which cleared the expiry — recreating the bug —
    and overwrote the stored lifetime, so even a later well-formed refresh had
    nothing left to fall back to. Strictly worse than the omitting case.
    """
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await cs.store_oauth(
        "c-13626f",
        "u1",
        "gitlab",
        {"access_token": "old", "refresh_token": "rt", "expires_in": 3600},
        "cid",
        "csec",
        "https://token",
        ["s"],
    )
    bundle = json.loads(store[secret_id]["value"])
    bundle["access_token_expires_at"] = (now_utc() - timedelta(seconds=1)).isoformat()
    store[secret_id]["value"] = json.dumps(bundle)

    from knowledge.connectors import oauth_flow

    async def _refresh_malformed(token_url, client_id, client_secret, refresh_token):
        return {"access_token": "new", "expires_in": bad_expires_in}

    monkeypatch.setattr(oauth_flow, "refresh_access_token", _refresh_malformed)
    assert await cs.get_access_token(secret_id, "u1") == "new"

    refreshed = json.loads(store[secret_id]["value"])
    assert refreshed["access_token_lifetime_seconds"] == 3600, "stored lifetime destroyed by a malformed value"
    assert refreshed["access_token_expires_at"] is not None, "expiry cleared — refresh disabled forever"
    assert parse_utc_iso(refreshed["access_token_expires_at"]) > now_utc() + timedelta(seconds=3000)


@pytest.mark.asyncio
async def test_credential_without_recorded_owner_is_denied_everywhere():
    """#13628: a missing ``created_by`` must fail closed at all three guard sites.

    The old guard was ``if stored_owner and stored_owner != owner_id``, so an
    empty owner skipped the comparison and *any* caller could read, rotate or
    refresh the credential. This guard is the only per-user boundary on a
    decrypted connector secret; static credentials and rows migrated by
    ``scripts/migrate_connector_credentials.py`` can carry an empty owner.
    """
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await cs.store_oauth(
        "c-13628",
        "u1",
        "gitlab",
        {"access_token": "tok", "refresh_token": "rt", "expires_in": 3600},
        "cid",
        "csec",
        "https://token",
        ["s"],
    )
    # Model an unattributable credential.
    store[secret_id]["created_by"] = ""

    # Lazily, so one site's failure cannot mask the others.
    sites = {
        "load": lambda: cs.load(secret_id, {}, MagicMock(), "anyone"),
        "rotate": lambda: cs.rotate(secret_id, {"access_token": "new"}, "anyone"),
        "get_access_token": lambda: cs.get_access_token(secret_id, "anyone"),
    }
    for label, call in sites.items():
        with pytest.raises(PermissionError, match="no recorded owner"):
            await call()
        assert label in sites


@pytest.mark.asyncio
async def test_rotate_attributes_the_decrypt_to_the_caller():
    """#13628: rotation decrypts the full bundle and must leave an audit trail.

    ``accessed_by`` is what drives ``_update_access_tracking`` in
    ``secrets_service``. ``load`` and ``get_access_token`` both pass it; ``rotate``
    did not, so the one privileged read path that exposes the whole plaintext
    bundle was the one with no attribution. Nothing failed when it was dropped,
    which is why this needs pinning.
    """
    svc, _ = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await cs.store_oauth(
        "c-13628b",
        "u1",
        "gitlab",
        {"access_token": "tok", "refresh_token": "rt", "expires_in": 3600},
        "cid",
        "csec",
        "https://token",
        ["s"],
    )
    svc.get_secret.reset_mock()

    await cs.rotate(secret_id, {"access_token": "rotated"}, "u1")

    decrypting = [c for c in svc.get_secret.call_args_list if c.kwargs.get("include_value")]
    assert decrypting, "rotate did not read the secret value"
    assert all(
        c.kwargs.get("accessed_by") == "u1" for c in decrypting
    ), f"decrypt not attributed: {[c.kwargs.get('accessed_by') for c in decrypting]}"


@pytest.mark.asyncio
async def test_owner_with_recorded_id_still_works():
    """#13628 guard must not break the ordinary attributed path."""
    svc, _ = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await cs.store_oauth(
        "c-13628c",
        "u1",
        "gitlab",
        {"access_token": "tok", "refresh_token": "rt", "expires_in": 3600},
        "cid",
        "csec",
        "https://token",
        ["s"],
    )
    assert await cs.get_access_token(secret_id, "u1") == "tok"
    await cs.rotate(secret_id, {"access_token": "tok2"}, "u1")
    assert await cs.get_access_token(secret_id, "u1") == "tok2"


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

# ---------------------------------------------------------------------------
# #13627: refresh serialization
# ---------------------------------------------------------------------------


async def _expired_oauth_secret(cs, store, name):
    secret_id = await cs.store_oauth(
        name, "u1", "gitlab",
        {"access_token": "old", "refresh_token": "rt-old", "expires_in": 3600},
        "cid", "csec", "https://token", ["s"],
    )
    bundle = json.loads(store[secret_id]["value"])
    bundle["access_token_expires_at"] = (now_utc() - timedelta(seconds=1)).isoformat()
    store[secret_id]["value"] = json.dumps(bundle)
    return secret_id


@pytest.mark.asyncio
async def test_concurrent_refresh_calls_the_token_endpoint_once(monkeypatch):
    """#13627: two concurrent callers must produce exactly ONE refresh.

    With a rotating-refresh-token provider, two refreshes issue two successors;
    the second write wins and the stored token may not be the provider's valid
    one, so the next refresh fails permanently and the user must re-authorize.
    """
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await _expired_oauth_secret(cs, store, "c-13627")

    from knowledge.connectors import oauth_flow

    calls = []

    async def _slow_refresh(token_url, client_id, client_secret, refresh_token):
        calls.append(refresh_token)
        await asyncio.sleep(0.05)  # hold the lease long enough for the loser to queue
        return {"access_token": "new", "refresh_token": "rt-new", "expires_in": 3600}

    monkeypatch.setattr(oauth_flow, "refresh_access_token", _slow_refresh)

    # Simulate an available lock: first acquisition wins, later ones lose.
    holders = {"taken": False}

    async def _fake_leadership(self, *a, **kw):
        if holders["taken"]:
            return False
        holders["taken"] = True
        self._is_leader = True
        return True

    async def _fake_release(self):
        holders["taken"] = False
        self._is_leader = False

    monkeypatch.setattr(LeaderLease, "update_leadership", _fake_leadership)
    monkeypatch.setattr(LeaderLease, "release", _fake_release)
    monkeypatch.setattr(ConnectorCredentialStore, "_refresh_lock_available", staticmethod(AsyncMock(return_value=True)))

    a, b = await asyncio.gather(
        cs.get_access_token(secret_id, "u1"),
        cs.get_access_token(secret_id, "u1"),
    )

    assert len(calls) == 1, f"token endpoint called {len(calls)} times — refresh not serialized"
    assert a == b == "new", f"callers disagreed: {a!r} vs {b!r}"


@pytest.mark.asyncio
async def test_lock_wait_timeout_raises_instead_of_refreshing_unsynchronized(monkeypatch):
    """#13627: the loser must fail loudly, never fall through to its own refresh."""
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await _expired_oauth_secret(cs, store, "c-13627b")

    from knowledge.connectors import oauth_flow

    called = []

    async def _must_not_run(*a, **kw):
        called.append(1)
        return {"access_token": "should-never-happen"}

    monkeypatch.setattr(oauth_flow, "refresh_access_token", _must_not_run)
    monkeypatch.setattr(LeaderLease, "update_leadership", AsyncMock(return_value=False))
    monkeypatch.setattr(ConnectorCredentialStore, "_refresh_lock_available", staticmethod(AsyncMock(return_value=True)))
    monkeypatch.setattr(mod, "_REFRESH_WAIT_S", 0.3)
    monkeypatch.setattr(mod, "_REFRESH_POLL_S", 0.05)

    with pytest.raises(TimeoutError, match="concurrent OAuth refresh"):
        await cs.get_access_token(secret_id, "u1")
    assert not called, "loser called the token endpoint — the race is still open"


@pytest.mark.asyncio
async def test_without_redis_refresh_proceeds_rather_than_failing(monkeypatch):
    """#13627: no Redis must not mean no connector auth.

    LeaderLease reports "another holder" and "no Redis" identically. Treating the
    latter as the former made every refresh wait then fail — a total outage
    wherever Redis is absent, which is far worse than the race being fixed.
    """
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    secret_id = await _expired_oauth_secret(cs, store, "c-13627c")

    from knowledge.connectors import oauth_flow

    monkeypatch.setattr(
        oauth_flow, "refresh_access_token",
        AsyncMock(return_value={"access_token": "new", "expires_in": 3600}),
    )
    monkeypatch.setattr(LeaderLease, "update_leadership", AsyncMock(return_value=False))
    monkeypatch.setattr(ConnectorCredentialStore, "_refresh_lock_available", staticmethod(AsyncMock(return_value=False)))

    assert await cs.get_access_token(secret_id, "u1") == "new"
