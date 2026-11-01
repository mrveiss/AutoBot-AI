# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Changing a chat-approval setting leaves an audit row: who, when, old and new value (#20465).

``api/settings.py`` is loaded by path with its database, auth and ORM imports stubbed (the
package conftest replaces ``sqlalchemy``/``models``/``services`` with spec-less mocks), mirroring
``test_llm_config_round_trip_17826.py``. FastAPI, pydantic and the route bodies are real. Every
stub goes through ``monkeypatch`` and is withdrawn after the test.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import BaseModel  # noqa: E402

_BACKEND = Path(__file__).resolve().parents[2]
_RELAXED = "chat.relaxed_approval_categories"
_AUTO = "chat.auto_approve_attachment_turns"


class _Key:
    def __eq__(self, other):  # type: ignore[override]
        return other


class _Setting:
    key = _Key()

    def __init__(self, key: str, value: str, description: str | None = None):
        self.key, self.value, self.description = key, value, description


class _Select:
    def __init__(self, _model):
        self.wanted = None

    def where(self, condition):
        self.wanted = condition
        return self

    def order_by(self, *_a):
        return self


class _Db:
    """Settings rows plus a log of what happened, so order (audit before commit) is assertable."""

    def __init__(self, rows: dict[str, str]):
        self.rows = {k: _Setting(k, v) for k, v in rows.items()}
        self.events: list[str] = []

    async def execute(self, statement):
        row = self.rows.get(statement.wanted)
        return SimpleNamespace(scalar_one_or_none=lambda: row)

    def add(self, row):
        self.rows[row.key] = row

    async def delete(self, row):
        self.rows.pop(row.key, None)

    async def commit(self):
        self.events.append("commit")

    async def refresh(self, _row):
        return None


class _SettingResponse(BaseModel):
    model_config = {"from_attributes": True}
    key: str
    value: str
    description: str | None = None


class _SettingUpdate(BaseModel):
    value: str
    description: str | None = None


def _module(monkeypatch, name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    for attr, value in attrs.items():
        setattr(mod, attr, value)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


async def _no_db():
    yield None


@pytest.fixture()
def build(monkeypatch):
    audit_rows: list[dict] = []
    state = {"db": None, "fail_audit": False}

    async def _audit(db, **row):
        if state["fail_audit"]:
            raise RuntimeError("audit store down")
        db.events.append("audit")
        audit_rows.append(row)

    async def _admin() -> dict:
        return {"sub": "alice", "role": "admin"}

    _module(monkeypatch, "sqlalchemy", select=_Select)
    _module(monkeypatch, "sqlalchemy.ext")
    _module(monkeypatch, "sqlalchemy.ext.asyncio", AsyncSession=type("AsyncSession", (), {}))
    _module(monkeypatch, "models")
    _module(monkeypatch, "models.database", Node=object, Setting=_Setting)
    _module(monkeypatch, "models.schemas", SettingResponse=_SettingResponse, SettingUpdate=_SettingUpdate)
    _module(monkeypatch, "services")
    _module(monkeypatch, "services.auth", get_current_user=_admin, require_permission=lambda _p: _admin)
    _module(monkeypatch, "services.database", get_db=_no_db)
    _module(monkeypatch, "services.playbook_executor", get_playbook_executor=lambda: None)
    _module(monkeypatch, "api")
    _module(monkeypatch, "api.security", create_audit_log=_audit)
    _module(monkeypatch, "autobot_shared")
    _module(monkeypatch, "autobot_shared.auth")
    perm = SimpleNamespace(ADMIN_CONFIG_WRITE="admin:config:write")
    _module(monkeypatch, "autobot_shared.auth.permissions", Permission=perm)

    spec = importlib.util.spec_from_file_location("_settings_under_test_20465", _BACKEND / "api/settings.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    monkeypatch.setitem(sys.modules, "_settings_under_test_20465", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    def make(db: _Db) -> TestClient:
        app = FastAPI()
        app.include_router(mod.router)

        async def _db():
            yield db

        app.dependency_overrides[_no_db] = _db
        return TestClient(app)

    return make, audit_rows, state


def test_changing_the_relaxed_categories_records_who_old_and_new(build):
    make, audit_rows, _ = build
    db = _Db({_RELAXED: '["pushing commits"]'})
    new = '["pushing commits", "sending externally"]'

    resp = make(db).put(f"/settings/{_RELAXED}", json={"value": new})

    assert resp.status_code == 200, resp.text
    assert len(audit_rows) == 1
    row = audit_rows[0]
    assert (row["username"], row["user_id"]) == ("alice", "alice")
    assert (row["category"], row["action"]) == ("configuration", "setting.update")
    assert (row["resource_type"], row["resource_id"]) == ("setting", _RELAXED)
    assert row["extra_data"] == {"key": _RELAXED, "old_value": '["pushing commits"]', "new_value": new}
    assert db.events == ["audit", "commit"], "the audit row joins the change's transaction, before the commit"


def test_creating_and_deleting_the_auto_approve_flag_are_audited(build):
    make, audit_rows, _ = build
    db = _Db({})
    client = make(db)

    assert client.post(f"/settings/{_AUTO}", json={"value": '{"enabled": true}'}).status_code == 201
    assert client.delete(f"/settings/{_AUTO}").status_code == 204

    assert [r["action"] for r in audit_rows] == ["setting.create", "setting.delete"]
    assert audit_rows[0]["extra_data"]["old_value"] is None
    assert audit_rows[0]["extra_data"]["new_value"] == '{"enabled": true}'
    assert audit_rows[1]["extra_data"]["old_value"] == '{"enabled": true}'
    assert audit_rows[1]["extra_data"]["new_value"] is None


def test_other_keys_are_not_audited_so_no_unrelated_value_reaches_the_audit_log(build):
    make, audit_rows, _ = build
    db = _Db({"api_token": "s3cret"})  # pragma: allowlist secret

    assert make(db).put("/settings/api_token", json={"value": "rotated"}).status_code == 200

    assert audit_rows == []


def test_an_unwritable_audit_row_means_the_change_is_not_committed(build):
    make, _, state = build
    state["fail_audit"] = True
    db = _Db({_AUTO: "true"})

    with pytest.raises(RuntimeError):
        make(db).put(f"/settings/{_AUTO}", json={"value": '{"enabled": false}'})

    assert "commit" not in db.events
