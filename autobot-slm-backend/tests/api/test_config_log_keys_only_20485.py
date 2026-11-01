# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Setting a global or per-node config logs the key, never the value (#20485).

``api/config.py`` is loaded by path with its ORM, auth and database imports
stubbed, as in ``test_settings_log_keys_only_20485.py``.
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
from pydantic import BaseModel, ConfigDict

_BACKEND = Path(__file__).resolve().parents[2]
# Looks like a credential to a reader and to a scanner; built at runtime, never stored.
VALUE_MARKER = "-".join(["sk", "live", "do", "not", "log", "20485"])


class _Response(BaseModel):
    model_config = ConfigDict(extra="allow")


class _Request(BaseModel):
    value: str
    value_type: str = "string"


def _module(monkeypatch, name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    for attr, value in attrs.items():
        setattr(mod, attr, value)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


@pytest.fixture()
def config_mod(monkeypatch):
    _module(monkeypatch, "sqlalchemy", select=lambda *_a: SimpleNamespace(where=lambda *_b: None))
    _module(monkeypatch, "sqlalchemy.ext")
    _module(monkeypatch, "sqlalchemy.ext.asyncio", AsyncSession=type("AsyncSession", (), {}))
    _module(monkeypatch, "models")
    _module(monkeypatch, "models.database", Node=MagicMock(), NodeConfig=MagicMock())
    _module(
        monkeypatch,
        "models.schemas",
        NodeConfigBulkResponse=_Response,
        NodeConfigResponse=_Response,
        NodeConfigSetRequest=_Request,
    )
    _module(monkeypatch, "services")
    _module(monkeypatch, "services.auth", get_current_user=lambda: None)
    _module(monkeypatch, "services.database", get_db=lambda: None)
    spec = importlib.util.spec_from_file_location("_config_under_test_20485", _BACKEND / "api/config.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    monkeypatch.setitem(sys.modules, spec.name, mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _db():
    row = SimpleNamespace(
        id=1,
        node_id="node-1",
        config_key="k",
        config_value="old",
        value_type="string",
        created_at=None,
        updated_at=None,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_global_default_logs_key_not_value(config_mod, caplog):
    req = _Request(value=VALUE_MARKER)
    with caplog.at_level(logging.DEBUG):
        await config_mod.set_global_default("some.key", req, _db(), {})
    assert "some.key" in caplog.text
    assert VALUE_MARKER not in caplog.text


@pytest.mark.asyncio
async def test_node_config_logs_key_not_value(config_mod, caplog):
    req = _Request(value=VALUE_MARKER)
    with caplog.at_level(logging.DEBUG):
        await config_mod.set_node_config_key("node-1", "some.key", req, _db(), {})
    assert "some.key" in caplog.text
    assert VALUE_MARKER not in caplog.text
