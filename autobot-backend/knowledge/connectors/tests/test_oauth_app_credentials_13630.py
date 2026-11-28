# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""OAuth refresh resolves the app's client credentials from config (#13630)."""

import json
from unittest.mock import MagicMock

import pytest

from knowledge.connectors.credential_store import ConnectorCredentialStore


@pytest.fixture(autouse=True)
def _configured_oauth_app(monkeypatch):
    from knowledge.connectors import oauth_flow

    monkeypatch.setattr(oauth_flow, "resolve_client_credentials", lambda p: ("cid", "csec"))


def _make_svc():
    """A SecretsService double backed by a dict."""
    svc = MagicMock()
    store = {}

    def _create(name, secret_type, value, scope, created_by=None, **_):
        sid = f"sid-{name}"
        store[sid] = {"id": sid, "name": name, "value": value, "created_by": created_by}
        return {"id": sid}

    def _get(secret_id=None, include_value=False, **_):
        return dict(store[secret_id]) if secret_id in store else None

    def _update(secret_id, value=None, **_):
        store[secret_id]["value"] = value
        return True

    svc.create_secret.side_effect = _create
    svc.get_secret.side_effect = _get
    svc.update_secret.side_effect = _update
    return svc, store


# ---------------------------------------------------------------------------
# #13630: refresh resolves the app credentials at use time
# ---------------------------------------------------------------------------


async def _expired_bundle(cs, store, extra=None):
    sid = await cs.store_oauth(
        "c", "u1", "gitlab", {"access_token": "o", "refresh_token": "rt", "expires_in": 0}, "https://t", ["s"]
    )
    if extra:
        bundle = json.loads(store[sid]["value"])
        bundle.update(extra)
        store[sid]["value"] = json.dumps(bundle)
    return sid


def _capture_refresh(monkeypatch):
    from knowledge.connectors import oauth_flow

    seen = {}

    async def _fake(token_url, client_id, client_secret, refresh_token, **_kw):
        seen.update(client_id=client_id, client_secret=client_secret)
        return {"access_token": "new", "expires_in": 3600}

    monkeypatch.setattr(oauth_flow, "refresh_access_token", _fake)
    return seen


@pytest.mark.asyncio
async def test_a_new_bundle_carries_no_app_credentials():
    svc, store = _make_svc()
    sid = await _expired_bundle(ConnectorCredentialStore(svc), store)
    bundle = json.loads(store[sid]["value"])
    assert "client_secret" not in bundle and "client_id" not in bundle
    assert bundle["provider"] == "gitlab" and bundle["token_url"] == "https://t"


@pytest.mark.asyncio
async def test_refresh_of_a_new_bundle_uses_the_configured_credentials(monkeypatch):
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    sid = await _expired_bundle(cs, store)
    seen = _capture_refresh(monkeypatch)
    assert await cs.get_access_token(sid, "u1") == "new"
    assert (seen["client_id"], seen["client_secret"]) == ("cid", "csec")


@pytest.mark.asyncio
async def test_refresh_of_a_legacy_bundle_prefers_the_rotated_config(monkeypatch):
    """The rotation test: the stale stored copy must lose to the configured value."""
    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    sid = await _expired_bundle(cs, store, {"client_id": "cid-old", "client_secret": "csec-OLD"})
    seen = _capture_refresh(monkeypatch)
    await cs.get_access_token(sid, "u1")
    assert seen == {"client_id": "cid", "client_secret": "csec"}


@pytest.mark.asyncio
async def test_a_legacy_bundle_without_config_falls_back_with_a_warning(monkeypatch, caplog):
    from knowledge.connectors import oauth_flow

    def _unconfigured(_p):
        raise ValueError("not configured")

    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    sid = await _expired_bundle(cs, store, {"client_id": "cid-old", "client_secret": "csec-OLD"})
    monkeypatch.setattr(oauth_flow, "resolve_client_credentials", _unconfigured)
    seen = _capture_refresh(monkeypatch)
    with caplog.at_level("DEBUG"):
        await cs.get_access_token(sid, "u1")
    assert seen == {"client_id": "cid-old", "client_secret": "csec-OLD"}
    warnings = [r for r in caplog.records if r.levelname == "WARNING" and "legacy" in r.getMessage()]
    assert warnings
    for value in ("csec-OLD", "cid-old", "rt"):
        assert value not in caplog.text


@pytest.mark.asyncio
async def test_a_new_bundle_without_config_fails_clearly(monkeypatch):
    from knowledge.connectors import oauth_flow

    def _unconfigured(_p):
        raise ValueError("not configured")

    svc, store = _make_svc()
    cs = ConnectorCredentialStore(svc)
    sid = await _expired_bundle(cs, store)
    monkeypatch.setattr(oauth_flow, "resolve_client_credentials", _unconfigured)
    _capture_refresh(monkeypatch)
    with pytest.raises(ValueError, match="not configured"):
        await cs.get_access_token(sid, "u1")
