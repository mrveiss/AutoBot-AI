# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The PBKDF2 activation instant is recorded once and drives the cutoff (#20611)."""

import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_KEY = "api_key_pbkdf2_active_since"


class _Result:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Db:
    def __init__(self, rows):
        self.rows = rows
        self.committed = 0

    async def execute(self, _query):
        return _Result(self.rows.get(_KEY))

    def begin_nested(self):
        return _Nested()

    def add(self, row):
        self.rows[row.key] = row

    async def commit(self):
        self.committed += 1


class _Ctx:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def clock(monkeypatch):
    rows = {}
    db = _Db(rows)
    fakes = {
        "services.database": SimpleNamespace(db_service=SimpleNamespace(session=lambda: _Ctx(db))),
        "models.database": SimpleNamespace(
            Setting=type("Setting", (), {"key": _KEY, "__init__": lambda self, **kw: self.__dict__.update(kw)})
        ),
    }
    for name, attrs in fakes.items():
        mod = types.ModuleType(name)
        mod.__dict__.update(vars(attrs))
        monkeypatch.setitem(sys.modules, name, mod)
    spec = importlib.util.spec_from_file_location("_scheme_clock_20611", _ROOT / "services/api_key_scheme_clock.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "select", lambda *_a: SimpleNamespace(where=lambda *_b: None))
    return mod, db


def test_first_call_records_the_instant_and_later_calls_keep_it(clock):
    mod, db = clock
    first = asyncio.run(mod.scheme_active_since())
    assert db.rows[_KEY].value == first.isoformat() and db.committed == 1
    mod.reset_cache()
    assert asyncio.run(mod.scheme_active_since()) == first
    assert db.committed == 1


def test_cutoff_is_thirty_days_after_activation(clock):
    mod, _ = clock
    start = datetime(2026, 11, 6, tzinfo=timezone.utc)
    assert mod.LEGACY_CUTOFF_DAYS == 30
    assert not mod.cutoff_passed(start, start + timedelta(days=29, hours=23))
    assert mod.cutoff_passed(start, start + timedelta(days=30))
