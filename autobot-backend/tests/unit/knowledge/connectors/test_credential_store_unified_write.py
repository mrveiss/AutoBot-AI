# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Routing tests for the ConnectorCredentialStore dual-write flag (#10088 / Task 3c-2).

Verifies the expand-phase write flag: off → no vault mirror (byte-identical to before);
on → each write also mirrors/deletes in the vault store. The mirror core itself is
exercised against Postgres in tests/migrations/test_credential_mirror.py.
"""

import json

from knowledge.connectors import credential_store as cs
from knowledge.connectors.credential_store import ConnectorCredentialStore


class _Auth:
    __sensitive_fields__ = frozenset({"token"})


class _FakeSvc:
    def create_secret(self, **kw):
        return {"id": "sid-1"}

    def get_secret(self, **kw):
        return {"created_by": "u1", "value": json.dumps({"token": "x"})}

    def update_secret(self, **kw):
        return None

    def delete_secret(self, **kw):
        return None


def test_write_flag_parsing(monkeypatch):
    monkeypatch.delenv(cs.VAULT_WRITE_ENV, raising=False)
    assert cs._vault_write_enabled() is False
    monkeypatch.setenv(cs.VAULT_WRITE_ENV, "true")
    assert cs._vault_write_enabled() is True
    monkeypatch.setenv(cs.VAULT_WRITE_ENV, "0")
    assert cs._vault_write_enabled() is False


async def test_store_flag_off_no_mirror(monkeypatch):
    monkeypatch.setattr(cs, "_vault_write_enabled", lambda: False)
    calls = []

    async def _m(*a, **k):
        calls.append(a)

    monkeypatch.setattr(cs, "mirror_credential_to_vault", _m)
    sid, sanitized = await ConnectorCredentialStore(_FakeSvc()).store("c1", "u1", _Auth, {"token": "t", "host": "h"})
    assert sid == "sid-1" and sanitized == {"host": "h"} and calls == []


async def test_store_flag_on_mirrors_with_name(monkeypatch):
    monkeypatch.setattr(cs, "_vault_write_enabled", lambda: True)
    calls = []

    async def _m(sqlite_id, owner_id, value, *, name=None, secret_type=None):
        calls.append((sqlite_id, owner_id, name, json.loads(value)))

    monkeypatch.setattr(cs, "mirror_credential_to_vault", _m)
    await ConnectorCredentialStore(_FakeSvc()).store("c1", "u1", _Auth, {"token": "t", "host": "h"})
    assert calls == [("sid-1", "u1", "connector:c1:auth", {"token": "t"})]  # only the sensitive field


async def test_rotate_flag_on_mirrors_update(monkeypatch):
    monkeypatch.setattr(cs, "_vault_write_enabled", lambda: True)
    calls = []

    async def _m(sqlite_id, owner_id, value, *, name=None, secret_type=None):
        calls.append((sqlite_id, owner_id, name, json.loads(value)))

    monkeypatch.setattr(cs, "mirror_credential_to_vault", _m)
    await ConnectorCredentialStore(_FakeSvc()).rotate("sid-9", {"token": "new"}, "u1")
    assert calls == [("sid-9", "u1", None, {"token": "new"})]  # update path → no name


async def test_revoke_flag_on_deletes(monkeypatch):
    monkeypatch.setattr(cs, "_vault_write_enabled", lambda: True)
    calls = []

    async def _d(sqlite_id, owner_id):
        calls.append((sqlite_id, owner_id))

    monkeypatch.setattr(cs, "delete_credential_from_vault", _d)
    await ConnectorCredentialStore(_FakeSvc()).revoke("sid-9", "u1")
    assert calls == [("sid-9", "u1")]
