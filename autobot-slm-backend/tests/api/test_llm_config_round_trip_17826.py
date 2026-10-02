# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET then PUT /settings/admin/llm leaves every stored provider key untouched (#17826).

Saving any LLM setting used to overwrite every provider's stored key with its
display mask: GET masked the key, the settings page PUT the whole config back,
and the save stored the mask. Each test here GETs the config through a real
TestClient, makes one unrelated edit, PUTs the GET response back, and asserts
the stored secret reference is byte-identical and the vault was never written.
Both storage paths are covered: the unified vault and the inline-encryption
fallback used while the vault is not configured.

FastAPI, pydantic and ``llm_secrets.py`` are real, so response serialisation,
request validation and the merge are exercised end to end. ``api/llm_config.py``
is loaded by path with its database, auth and ORM imports stubbed -- the
package's own conftest replaces ``sqlalchemy``/``models``/``services`` with
spec-less mocks, which cannot tell one query from another -- mirroring
``tests/api/test_apply_secrets.py``. Every stub is installed through
``monkeypatch`` and withdrawn after the test.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_BACKEND = Path(__file__).resolve().parents[2]
_PATH = "/settings/admin/llm"
_SECRET_FIELDS = ("api_key", "api_key_vault_id", "api_key_ref")


class _Key:
    """Stands in for ``Setting.key``: records the two comparisons llm_config makes."""

    def __eq__(self, other):  # type: ignore[override]
        return ("eq", other)

    def startswith(self, prefix):
        return ("prefix", prefix)


class _Setting:
    key = _Key()

    def __init__(self, key: str, value: str, description: str = ""):
        self.key, self.value, self.description = key, value, description


class _Select:
    def __init__(self, _model):
        self.condition = None

    def where(self, condition):
        self.condition = condition
        return self


class _Db:
    def __init__(self, rows: dict[str, str]):
        self._rows = {k: _Setting(k, v) for k, v in rows.items()}

    def stored(self) -> dict:
        return {p["name"]: p for p in json.loads(self._rows["llm_providers"].value)}

    async def execute(self, statement: _Select):
        kind, arg = statement.condition
        hits = [r for k, r in self._rows.items() if (k == arg if kind == "eq" else k.startswith(arg))]
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: hits),
            scalar_one_or_none=lambda: hits[0] if hits else None,
        )

    def add(self, row: _Setting) -> None:
        self._rows[row.key] = row

    async def commit(self) -> None:
        return None


def _module(monkeypatch, name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []  # type: ignore[attr-defined]  # importable as a package parent
    for attr, value in attrs.items():
        setattr(mod, attr, value)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


def _load(monkeypatch, alias: str, relative: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(alias, _BACKEND / relative)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    monkeypatch.setitem(sys.modules, alias, mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


async def _allow() -> dict:
    return {"sub": "admin", "role": "admin"}


async def _no_db():
    yield None


def _install_stubs(monkeypatch, vault: SimpleNamespace) -> None:
    _module(monkeypatch, "sqlalchemy", select=_Select)
    _module(monkeypatch, "sqlalchemy.ext")
    _module(monkeypatch, "sqlalchemy.ext.asyncio", AsyncSession=type("AsyncSession", (), {}))
    _module(monkeypatch, "models")
    _module(monkeypatch, "models.database", Node=object, Setting=_Setting)
    _module(monkeypatch, "services")
    _module(monkeypatch, "services.auth", require_permission=lambda _permission: _allow)
    _module(monkeypatch, "services.database", get_db=_no_db)
    _module(monkeypatch, "services.encryption", encrypt_data=lambda v: f"ENC[{v}]", decrypt_data=lambda v: v)
    _module(monkeypatch, "services.playbook_executor", get_playbook_executor=lambda: None)
    _module(monkeypatch, "autobot_shared")
    _module(monkeypatch, "autobot_shared.auth")
    permission = SimpleNamespace(ADMIN_CONFIG_READ="admin:config:read", ADMIN_CONFIG_WRITE="admin:config:write")
    _module(monkeypatch, "autobot_shared.auth.permissions", Permission=permission)
    _module(monkeypatch, "autobot_shared.ssot_config", config=SimpleNamespace(llm=SimpleNamespace(ollama_endpoint="")))
    _module(monkeypatch, "user_management")
    _module(monkeypatch, "user_management.services")
    _module(
        monkeypatch,
        "user_management.services.vault_client",
        VaultClientError=RuntimeError,
        VaultSecretNotFound=LookupError,
        is_configured=lambda: vault.configured,
        vault_create=vault.create,
        vault_rotate=vault.rotate,
        vault_read=vault.read,
        vault_list=AsyncMock(return_value=[]),
    )
    _load(monkeypatch, "user_management.services.llm_secrets", "user_management/services/llm_secrets.py")


@pytest.fixture()
def vault() -> SimpleNamespace:
    return SimpleNamespace(configured=True, create=AsyncMock(), rotate=AsyncMock(), read=AsyncMock())


@pytest.fixture()
def client_for(monkeypatch, vault):
    _install_stubs(monkeypatch, vault)
    llm_config = _load(monkeypatch, "_llm_config_under_test_17826", "api/llm_config.py")

    def build(db: _Db) -> TestClient:
        app = FastAPI()
        app.include_router(llm_config.router)

        async def _db():
            yield db

        app.dependency_overrides[_no_db] = _db
        return TestClient(app)

    return build


def _round_trip(client: TestClient) -> tuple[dict, dict]:
    """GET, flip one unrelated field, PUT the GET response back."""
    got = client.get(_PATH)
    assert got.status_code == 200, got.text
    body = got.json()["config"]
    for provider in body["providers"]:
        assert not set(_SECRET_FIELDS) & set(provider), f"GET carries a secret field: {provider}"
    body["providers"][0]["enabled"] = not body["providers"][0]["enabled"]
    put = client.put(_PATH, json=body)
    assert put.status_code == 200, put.text
    return body, put.json()["config"]


def test_vault_path_round_trip_leaves_the_stored_reference_untouched(client_for, vault):
    before = {"name": "openai", "enabled": True, "api_key_vault_id": "4b8f1c2e-0000-4000-8000-000000000001"}
    before["api_key_ref"] = "llm:provider:openai:api_key"  # pragma: allowlist secret
    db = _Db({"llm_providers": json.dumps([before])})

    sent, returned = _round_trip(client_for(db))

    after = db.stored()["openai"]
    assert {k: after.get(k) for k in _SECRET_FIELDS} == {k: before.get(k) for k in _SECRET_FIELDS}
    assert after["enabled"] is sent["providers"][0]["enabled"], "the unrelated edit must still land"
    assert not set(_SECRET_FIELDS) & set(returned["providers"][0]), "PUT response carries a secret field"
    vault.create.assert_not_awaited()
    vault.rotate.assert_not_awaited()
    vault.read.assert_not_awaited()  # the settings API never resolves a key at all


def test_inline_encryption_path_round_trip_leaves_the_ciphertext_byte_identical(client_for, vault):
    vault.configured = False
    before = {"name": "openai", "enabled": True, "api_key": "gAAAAB-opaque-ciphertext"}  # pragma: allowlist secret
    db = _Db({"llm_providers": json.dumps([before])})

    _round_trip(client_for(db))

    assert db.stored()["openai"]["api_key"] == before["api_key"]
    vault.create.assert_not_awaited()
    vault.rotate.assert_not_awaited()


def test_a_display_mask_put_back_is_refused_and_nothing_is_written(client_for, vault):
    """A tab loaded before #17826 still holds the old masks in its state."""
    before = {"name": "openai", "enabled": True, "api_key_vault_id": "4b8f1c2e-0000-4000-8000-000000000002"}
    db = _Db({"llm_providers": json.dumps([before])})
    client = client_for(db)
    body = client.get(_PATH).json()["config"]
    body["providers"][0]["api_key"] = "sk-l...b3f2"  # pragma: allowlist secret

    put = client.put(_PATH, json=body)

    assert put.status_code == 422, put.text
    assert db.stored()["openai"] == before
    vault.create.assert_not_awaited()
    vault.rotate.assert_not_awaited()


def _saved(vault_id: str) -> _Db:
    return _Db({"llm_providers": json.dumps([{"name": "openai", "enabled": True, "api_key_vault_id": vault_id}])})


def test_a_put_carrying_a_new_key_rotates_it_and_does_not_echo_it(client_for, vault):
    vault_id = "4b8f1c2e-0000-4000-8000-000000000003"
    db = _saved(vault_id)
    client = client_for(db)
    body = client.get(_PATH).json()["config"]
    body["providers"][0]["api_key"] = "sk-rotated-0001"  # pragma: allowlist secret

    put = client.put(_PATH, json=body)

    assert put.status_code == 200, put.text
    assert "sk-rotated-0001" not in put.text, "PUT response echoes the submitted key"
    assert not set(_SECRET_FIELDS) & set(put.json()["config"]["providers"][0])
    vault.rotate.assert_awaited_once()
    assert vault.rotate.call_args.args[1] == "sk-rotated-0001"
    vault.create.assert_not_awaited()
    assert db.stored()["openai"]["api_key_vault_id"] == vault_id and "api_key" not in db.stored()["openai"]


@pytest.mark.parametrize("names", [["openai", "openai"], [""]])
def test_duplicate_or_empty_provider_names_are_refused(client_for, vault, names):
    """Secrets are matched by name: two providers sharing one would share -- and overwrite -- one secret."""
    db = _saved("4b8f1c2e-0000-4000-8000-000000000004")
    client = client_for(db)
    body = client.get(_PATH).json()["config"]
    body["providers"] = [{"name": n, "api_key": "sk-new-0002"} for n in names]  # pragma: allowlist secret

    put = client.put(_PATH, json=body)

    assert put.status_code == 422, put.text
    vault.create.assert_not_awaited()
    vault.rotate.assert_not_awaited()


def test_a_vault_outage_is_a_503_not_a_bare_500(client_for, vault):
    vault.rotate.side_effect = RuntimeError("vault down")  # the stub's VaultClientError
    db = _saved("4b8f1c2e-0000-4000-8000-000000000005")
    client = client_for(db)
    body = client.get(_PATH).json()["config"]
    body["providers"][0]["api_key"] = "sk-new-0003"  # pragma: allowlist secret

    put = client.put(_PATH, json=body)

    assert put.status_code == 503, put.text
    assert "vault down" not in put.text
