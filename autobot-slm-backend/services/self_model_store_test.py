# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The heartbeat fold of the self-model store: the stored inventory hash advances only when folded (#22280).

Loaded by path under a private name: the conftest stubs ``services.self_model_store`` for the real-loaded
reconciler, so this file loads the real module for its own scope and never registers it in ``sys.modules``.
``sqlalchemy.dialects.postgresql`` is stubbed only while it loads: a session-wide stub would shadow the real
dialect for the tests that swap the real ORM in (tests/api/_real_orm_import.py). Its SQL runs against the
conftest's sqlalchemy stubs; ``load_rows`` and ``persist`` are replaced with an in-memory table, so what is
checked is the fold itself.
"""

import asyncio
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import DataError

from services.self_model_reconcile import entity_key
from testkit.fake_async_session import FakeAsyncSession

_spec = importlib.util.spec_from_file_location(
    "_self_model_store_under_test", Path(__file__).with_name("self_model_store.py")
)
store = importlib.util.module_from_spec(_spec)
# Only these two keys are swapped and put back: patch.dict would also drop every module first imported here.
_DIALECT_STUBS = {"sqlalchemy.dialects": MagicMock(), "sqlalchemy.dialects.postgresql": MagicMock()}
_saved = {name: sys.modules.get(name) for name in _DIALECT_STUBS}
sys.modules.update(_DIALECT_STUBS)
try:
    _spec.loader.exec_module(store)
finally:
    for _name, _module in _saved.items():
        if _module is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _module

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
NODE = entity_key("node", "n1")
FULL = {"packages": {"git": "2.43"}, "commands": ["git"]}


@pytest.fixture
def beat(monkeypatch):
    """Send one heartbeat ``extra_data`` through the real fold; returns the node's stored hash after it."""
    rows: dict = {}

    async def _load_rows(_db, *_conditions):
        return dict(rows)

    async def _persist(_db, plan):
        rows.update({u["entity_key"]: u for u in plan.upserts})

    monkeypatch.setattr(store, "load_rows", _load_rows)
    monkeypatch.setattr(store, "persist", _persist)

    def _beat(extra: dict):
        asyncio.run(store.apply_heartbeat_inventory(None, "n1", extra, NOW))
        return rows[NODE]["attrs"].get("inventory_hash")

    return _beat


def test_a_full_inventory_stores_its_hash(beat):
    assert beat({"inventory_hash": "h1", "inventory": FULL}) == "h1"


def test_a_new_hash_without_its_inventory_does_not_advance_the_stored_hash(beat):
    beat({"inventory_hash": "h1", "inventory": FULL})
    assert beat({"inventory_hash": "h2"}) == "h1"  # the list for h2 never arrived: the next beat must resend it


def test_an_unchanged_hash_keeps_the_stored_hash(beat):
    beat({"inventory_hash": "h1", "inventory": FULL})
    assert beat({"inventory_hash": "h1"}) == "h1"


def test_a_malformed_inventory_does_not_advance_the_stored_hash(beat):
    beat({"inventory_hash": "h1", "inventory": FULL})
    assert beat({"inventory_hash": "h2", "inventory": "not-a-mapping"}) == "h1"


def test_the_next_full_inventory_advances_the_stored_hash(beat):
    beat({"inventory_hash": "h1", "inventory": FULL})
    beat({"inventory_hash": "h2"})
    assert beat({"inventory_hash": "h2", "inventory": {"packages": {"git": "2.44"}, "commands": ["git"]}}) == "h2"


def test_a_misshapen_inventory_does_not_advance_the_stored_hash(beat):
    beat({"inventory_hash": "h1", "inventory": FULL})
    assert beat({"inventory_hash": "h2", "inventory": {"packages": ["git"], "commands": ["git"]}}) == "h1"
    assert beat({"inventory_hash": "h3", "inventory": {"packages": {}, "commands": "git"}}) == "h1"


def test_a_bad_inventory_member_is_dropped_and_the_rest_still_advances_the_hash(beat):
    beat({"inventory_hash": "h1", "inventory": FULL})
    for n, bad in enumerate([None, "x" * 256, "  "], start=2):
        inventory = {"packages": {"git": "2.44"}, "commands": [bad, "git"]}
        assert beat({"inventory_hash": f"h{n}", "inventory": inventory}) == f"h{n}"


def test_only_the_good_members_are_observed(monkeypatch):
    inventory = {"packages": {"git": "1", "": "2"}, "commands": ["ls", None, "x" * 256]}
    assert store._readable("n1", inventory) == {"packages": {"git": "1"}, "commands": ["ls"]}


def test_the_ack_is_the_stored_hash_and_none_when_the_fold_failed(monkeypatch):
    async def _stored(_db, *_conditions):
        return {NODE: {"attrs": {"inventory_hash": "h1"}}}

    monkeypatch.setattr(store, "load_rows", _stored)
    assert asyncio.run(store.acknowledged_inventory_hash(None, "n1")) == "h1"

    async def _unreadable(_db, *_conditions):
        raise DataError("SELECT", {}, Exception("bad"))

    monkeypatch.setattr(store, "load_rows", _unreadable)
    assert asyncio.run(store.acknowledged_inventory_hash(None, "n1")) is None


def test_the_sweep_reads_its_candidates_under_a_row_lock(monkeypatch):
    monkeypatch.setattr(store, "_last_sweep", 0.0)
    seen = {}

    async def _load_rows(_db, *_conditions, lock=False):
        seen["lock"] = lock
        return {}

    monkeypatch.setattr(store, "load_rows", _load_rows)
    monkeypatch.setattr(store, "persist", AsyncMock())
    asyncio.run(store.sweep_stale(None, NOW))
    assert seen["lock"] is True


def test_a_failed_self_model_fold_keeps_the_capability_profile(monkeypatch):
    """Each half runs in its own SAVEPOINT: a DataError in the fold rolls back the fold alone (#22280)."""
    capability = AsyncMock()
    monkeypatch.setattr(store, "apply_capability_profile", capability)
    monkeypatch.setattr(store, "_fold_heartbeat", AsyncMock(side_effect=DataError("INSERT", {}, Exception("bad"))))
    session = FakeAsyncSession()
    asyncio.run(store.apply_heartbeat_extra_data(session, "n1", {"inventory_hash": "h1"}))
    capability.assert_awaited_once_with(session, "n1", {"inventory_hash": "h1"})
    assert session.rollbacks == 1
