# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The heartbeat fold of the self-model store: the stored inventory hash advances only when folded (#22280).

Loaded by path under a private name: the conftest stubs ``services.self_model_store`` for the real-loaded
reconciler, so this file loads the real module for its own scope and never registers it in ``sys.modules``.
Its SQL runs against the conftest's sqlalchemy stubs; ``load_rows`` and ``persist`` are replaced with an
in-memory table, so what is checked is the fold itself.
"""

import asyncio
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.self_model_reconcile import entity_key

_spec = importlib.util.spec_from_file_location(
    "_self_model_store_under_test", Path(__file__).with_name("self_model_store.py")
)
store = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(store)

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
