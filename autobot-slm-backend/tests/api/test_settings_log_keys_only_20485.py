# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Creating or updating a setting logs the key, never the value (#20485).

``api/settings.py`` is loaded by path with its ORM, auth and database imports
stubbed (the package conftest replaces them with spec-less mocks), mirroring
``test_llm_config_round_trip_17826.py``. Stubs go through ``monkeypatch``.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

_BACKEND = Path(__file__).resolve().parents[2]
# Looks like a credential to a reader and to a scanner; built at runtime, never stored.
VALUE_MARKER = "-".join(["sk", "live", "do", "not", "log", "20485"])


class _Response(BaseModel):
    @classmethod
    def model_validate(cls, obj, *a, **kw):  # type: ignore[override]
        return cls()


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _module(monkeypatch, name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    for attr, value in attrs.items():
        setattr(mod, attr, value)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


@pytest.fixture()
def settings_mod(monkeypatch):
    _module(monkeypatch, "sqlalchemy", select=lambda *_a: SimpleNamespace(where=lambda *_b: None))
    _module(monkeypatch, "sqlalchemy.ext")
    _module(monkeypatch, "sqlalchemy.ext.asyncio", AsyncSession=type("AsyncSession", (), {}))
    _module(monkeypatch, "models")
    _module(monkeypatch, "models.database", Node=object, Setting=MagicMock(key=MagicMock(), side_effect=_Row))
    _module(monkeypatch, "models.schemas", SettingResponse=_Response, SettingUpdate=object)
    _module(monkeypatch, "services")
    _module(monkeypatch, "services.auth", get_current_user=lambda: None, require_permission=lambda _p: (lambda: None))
    _module(monkeypatch, "services.database", get_db=lambda: None)
    _module(monkeypatch, "services.playbook_executor", get_playbook_executor=lambda: None)
    _module(monkeypatch, "autobot_shared")
    _module(monkeypatch, "autobot_shared.auth")
    perm = SimpleNamespace(ADMIN_CONFIG_READ="r", ADMIN_CONFIG_WRITE="w")
    _module(monkeypatch, "autobot_shared.auth.permissions", Permission=perm)
    # PR #20536 adds `from api.security import create_audit_log`; stub it so this survives that merge.
    _module(monkeypatch, "api.security", create_audit_log=AsyncMock())
    spec = importlib.util.spec_from_file_location("_settings_under_test_20485", _BACKEND / "api/settings.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    monkeypatch.setitem(sys.modules, spec.name, mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _db(existing):
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _data():
    return SimpleNamespace(value=VALUE_MARKER, description=None)


@pytest.mark.asyncio
async def test_update_logs_key_not_value(settings_mod, caplog):
    with caplog.at_level(logging.DEBUG):
        await settings_mod.update_setting("some.key", _data(), _db(_Row(value="old")), {})
    assert "some.key" in caplog.text
    assert VALUE_MARKER not in caplog.text


@pytest.mark.asyncio
async def test_create_logs_key_not_value(settings_mod, caplog):
    with caplog.at_level(logging.DEBUG):
        await settings_mod.create_setting("some.key", _data(), _db(None), {})
    assert "some.key" in caplog.text
    assert VALUE_MARKER not in caplog.text
