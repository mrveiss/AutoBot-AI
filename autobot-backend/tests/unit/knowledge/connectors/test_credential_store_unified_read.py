# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Routing tests for the ConnectorCredentialStore unified-read flag (#10088 / Task 3c-2).

Verifies the expand-phase feature flag: off → SQLite only (byte-identical to before);
on → unified store first with SQLite fallback. The unified core itself is exercised
against Postgres in tests/migrations/test_credential_store_unified_read.py.
"""

import json

from knowledge.connectors import credential_store as cs
from knowledge.connectors.credential_store import ConnectorCredentialStore


class _FakeSvc:
    """Stand-in for the sync SQLite SecretsService."""

    def __init__(self, secret=None):
        self._secret = secret
        self.get_calls = 0

    def get_secret(self, **kw):
        self.get_calls += 1
        return self._secret


def test_flag_parsing(monkeypatch):
    monkeypatch.delenv(cs.UNIFIED_READ_ENV, raising=False)
    assert cs._unified_read_enabled() is False
    for v in ("true", "1", "YES", " True "):
        monkeypatch.setenv(cs.UNIFIED_READ_ENV, v)
        assert cs._unified_read_enabled() is True
    for v in ("false", "0", "", "nope"):
        monkeypatch.setenv(cs.UNIFIED_READ_ENV, v)
        assert cs._unified_read_enabled() is False


async def test_load_flag_off_uses_sqlite_only(monkeypatch):
    monkeypatch.setattr(cs, "_unified_read_enabled", lambda: False)

    async def _boom(*a, **k):
        raise AssertionError("unified path must not be consulted when flag is off")

    monkeypatch.setattr(cs, "_load_credential_from_unified", _boom)
    svc = _FakeSvc({"created_by": "u1", "value": json.dumps({"token": "sqlite"})})
    out = await ConnectorCredentialStore(svc).load("sid", {"host": "h"}, object, "u1")
    assert out == {"host": "h", "token": "sqlite"} and svc.get_calls == 1


async def test_load_flag_on_prefers_unified(monkeypatch):
    monkeypatch.setattr(cs, "_unified_read_enabled", lambda: True)

    async def _unified(secret_id, owner_id):
        return {"created_by": owner_id, "value": json.dumps({"token": "unified"})}

    monkeypatch.setattr(cs, "_load_credential_from_unified", _unified)
    svc = _FakeSvc({"created_by": "u1", "value": json.dumps({"token": "sqlite"})})
    out = await ConnectorCredentialStore(svc).load("sid", {"host": "h"}, object, "u1")
    assert out == {"host": "h", "token": "unified"} and svc.get_calls == 0  # SQLite untouched


async def test_load_flag_on_falls_back_when_not_imported(monkeypatch):
    monkeypatch.setattr(cs, "_unified_read_enabled", lambda: True)

    async def _none(secret_id, owner_id):
        return None

    monkeypatch.setattr(cs, "_load_credential_from_unified", _none)
    svc = _FakeSvc({"created_by": "u1", "value": json.dumps({"token": "sqlite"})})
    out = await ConnectorCredentialStore(svc).load("sid", {"host": "h"}, object, "u1")
    assert out == {"host": "h", "token": "sqlite"} and svc.get_calls == 1
