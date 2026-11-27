# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""``get_all_facts`` paginates over eligible facts, not raw keys (#20866)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.ssot_config import config
from knowledge.fact_key_families import (
    FACT_COLLECTIONS_PREFIX,
    FACT_ORIGIN_SESSION_PREFIX,
    FACT_VERSION_META_PREFIX,
    FACT_VERSIONS_PREFIX,
)
from knowledge.fact_stream import get_facts_page, is_fact_key
from knowledge.facts import FactsMixin

_RESEARCH = config.research_quarantine_collection


def fake_fact_redis(rows: dict, scanned: list | None = None):
    """A Redis stub: ``scan_iter`` yields the keys of *rows*; a pipeline returns the hashes it was asked for."""

    async def scan_iter(match=None, count=None):
        for key in rows:
            if scanned is not None:
                scanned.append(key)
            yield key

    async def scan(cursor=0, match=None, count=None):
        return 0, list(rows)

    def pipeline():
        queued: list = []
        pipe = MagicMock()
        pipe.hgetall.side_effect = queued.append
        pipe.execute = AsyncMock(side_effect=lambda: [rows[k] for k in queued])
        return pipe

    client = MagicMock()
    client.scan_iter = scan_iter
    client.scan = scan
    client.pipeline = pipeline
    return client


def _row(collection=None) -> dict:
    meta = {"collection": collection} if collection else {}
    return {b"content": b"c", b"metadata": json.dumps(meta).encode()}


class _Store(FactsMixin):
    def __init__(self, rows: dict, scanned: list | None = None) -> None:
        self._redis = fake_fact_redis(rows, scanned)

    def ensure_initialized(self) -> None:
        """No-op."""

    def redis(self):
        return self._redis


def _rows(held: int, good: int) -> dict:
    rows = {"fact:held%02d" % i: _row(_RESEARCH) for i in range(held)}
    rows.update({"fact:good%02d" % i: _row() for i in range(good)})
    return rows


@pytest.mark.asyncio
async def test_quarantined_facts_filling_the_first_window_do_not_eat_the_limit():
    facts = await _Store(_rows(held=5, good=5)).get_all_facts(limit=3)
    assert [f["fact_id"] for f in facts] == ["good00", "good01", "good02"]


@pytest.mark.asyncio
async def test_offset_counts_eligible_facts_not_raw_keys():
    facts = await _Store(_rows(held=5, good=5)).get_all_facts(limit=2, offset=2)
    assert [f["fact_id"] for f in facts] == ["good02", "good03"]


@pytest.mark.asyncio
async def test_limit_none_returns_every_eligible_fact():
    facts = await _Store(_rows(held=3, good=4)).get_all_facts()
    assert len(facts) == 4


@pytest.mark.asyncio
async def test_scan_stops_once_the_page_is_full(monkeypatch):
    monkeypatch.setattr("knowledge.fact_stream.FACT_SCAN_BATCH_SIZE", 2)
    scanned: list = []
    store = _Store({"fact:g%02d" % i: _row() for i in range(50)}, scanned)
    await store.get_all_facts(limit=2)
    assert len(scanned) < 50


#: Real producers' ids: the Claude-memory importer, a connector source id, the external adapter families.
_COLON_IDS = ["claude_memory:u1:slug", "gdrive:conn1:file:/docs/a.md", "ext:feed:42", "stream:s1:7"]
_NON_HASH_PREFIXES = [
    FACT_COLLECTIONS_PREFIX,
    FACT_ORIGIN_SESSION_PREFIX,
    FACT_VERSIONS_PREFIX,
    FACT_VERSION_META_PREFIX,
]


class _HashesOnly(dict):
    """Rows keyed by fact key; reading a non-hash family (Redis WRONGTYPE) fails the whole batch."""

    def __getitem__(self, key):
        if key.startswith(tuple(_NON_HASH_PREFIXES)):
            raise AssertionError("a non-hash fact: key was read as a hash: %s" % key)
        return super().__getitem__(key)


def _mixed_rows() -> dict:
    rows = _HashesOnly({"fact:plain01": _row()})
    rows.update({"fact:" + fid: _row() for fid in _COLON_IDS})
    rows.update({p + "plain01": _row() for p in _NON_HASH_PREFIXES})
    return rows


@pytest.mark.parametrize("fid", _COLON_IDS)
def test_a_fact_with_a_colon_id_is_a_fact_key(fid):
    assert is_fact_key("fact:" + fid) and is_fact_key(("fact:" + fid).encode())


@pytest.mark.parametrize("prefix", _NON_HASH_PREFIXES)
def test_each_non_hash_fact_family_is_not_a_fact_key(prefix):
    assert not is_fact_key(prefix + "abc") and not is_fact_key((prefix + "abc:def").encode())


@pytest.mark.asyncio
async def test_facts_already_stored_under_colon_ids_are_listed_with_their_full_id():
    facts = await _Store(_mixed_rows()).get_all_facts()
    assert sorted(f["fact_id"] for f in facts) == sorted(["plain01", *_COLON_IDS])


@pytest.mark.asyncio
async def test_a_scan_page_lists_colon_ids_and_skips_every_non_hash_family():
    cursor, facts = await get_facts_page(_Store(_mixed_rows()), 0, 100)
    assert cursor == 0 and sorted(f["fact_id"] for f in facts) == sorted(["plain01", *_COLON_IDS])
