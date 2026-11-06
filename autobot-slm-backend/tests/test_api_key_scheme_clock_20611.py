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

from testkit.fake_async_session import FakeAsyncSession

_ROOT = Path(__file__).resolve().parents[1]
_KEY = "api_key_pbkdf2_active_since"


class _Ctx:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def clock(monkeypatch):
    created = []

    class _Setting:
        key = _KEY

        def __init__(self, **kw):
            self.__dict__.update(kw)
            created.append(self)

    # 1st read: no row; then the stored row is read back after the insert, and on every later read.
    db = FakeAsyncSession(results=[[], lambda _s: created[:1], lambda _s: created[:1]])
    fakes = {
        "services.database": SimpleNamespace(db_service=SimpleNamespace(session=lambda: _Ctx(db))),
        "models.database": SimpleNamespace(Setting=_Setting),
    }
    for name, attrs in fakes.items():
        mod = types.ModuleType(name)
        mod.__dict__.update(vars(attrs))
        monkeypatch.setitem(sys.modules, name, mod)
    spec = importlib.util.spec_from_file_location("_scheme_clock_20611", _ROOT / "services/api_key_scheme_clock.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "select", lambda *_a: SimpleNamespace(where=lambda *_b: None))
    return mod, db, created


def test_first_call_records_the_instant_and_later_calls_keep_it(clock):
    mod, db, created = clock
    first = asyncio.run(mod.scheme_active_since())
    assert len(created) == 1 and created[0].value == first.isoformat() and db.committed
    mod.reset_cache()
    assert asyncio.run(mod.scheme_active_since()) == first
    assert len(created) == 1


def test_cutoff_is_thirty_days_after_activation(clock):
    mod, *_ = clock
    start = datetime(2026, 11, 6, tzinfo=timezone.utc)
    assert mod.LEGACY_CUTOFF_DAYS == 30
    assert not mod.cutoff_passed(start, start + timedelta(days=29, hours=23))
    assert mod.cutoff_passed(start, start + timedelta(days=30))
