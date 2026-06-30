# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Routing tests for the ConnectorCredentialStore vault-read flag (#10088 / Task 3c-2).

Verifies the expand-phase feature flag: off → SQLite only (byte-identical to before);
on → vault envelope store first with SQLite fallback. The vault core itself is exercised
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
    monkeypatch.delenv(cs.VAULT_READ_ENV, raising=False)
    assert cs._vault_read_enabled() is False
    for v in ("true", "1", "YES", " True "):
        monkeypatch.setenv(cs.VAULT_READ_ENV, v)
        assert cs._vault_read_enabled() is True
    for v in ("false", "0", "", "nope"):
        monkeypatch.setenv(cs.VAULT_READ_ENV, v)
        assert cs._vault_read_enabled() is False


async def test_load_flag_off_uses_sqlite_only(monkeypatch):
    monkeypatch.setattr(cs, "_vault_read_enabled", lambda: False)

    async def _boom(*a, **k):
        raise AssertionError("vault path must not be consulted when flag is off")

    monkeypatch.setattr(cs, "load_imported_credential", _boom)
    svc = _FakeSvc({"created_by": "u1", "value": json.dumps({"token": "sqlite"})})
    out = await ConnectorCredentialStore(svc).load("sid", {"host": "h"}, object, "u1")
    assert out == {"host": "h", "token": "sqlite"} and svc.get_calls == 1


async def test_load_flag_on_prefers_vault(monkeypatch):
    monkeypatch.setattr(cs, "_vault_read_enabled", lambda: True)

    async def _vault(secret_id, owner_id):
        return {"created_by": owner_id, "value": json.dumps({"token": "vault"})}

    monkeypatch.setattr(cs, "load_imported_credential", _vault)
    svc = _FakeSvc({"created_by": "u1", "value": json.dumps({"token": "sqlite"})})
    out = await ConnectorCredentialStore(svc).load("sid", {"host": "h"}, object, "u1")
    assert out == {"host": "h", "token": "vault"} and svc.get_calls == 0  # SQLite untouched


async def test_load_flag_on_falls_back_when_not_imported(monkeypatch):
    monkeypatch.setattr(cs, "_vault_read_enabled", lambda: True)

    async def _none(secret_id, owner_id):
        return None

    monkeypatch.setattr(cs, "load_imported_credential", _none)
    svc = _FakeSvc({"created_by": "u1", "value": json.dumps({"token": "sqlite"})})
    out = await ConnectorCredentialStore(svc).load("sid", {"host": "h"}, object, "u1")
    assert out == {"host": "h", "token": "sqlite"} and svc.get_calls == 1
