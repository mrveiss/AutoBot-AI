# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""``get_all_facts`` paginates over eligible facts, not raw keys (#20866)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.ssot_config import config
from knowledge.facts import FactsMixin

_RESEARCH = config.research_quarantine_collection


def fake_fact_redis(rows: dict, scanned: list | None = None):
    """A Redis stub: ``scan_iter`` yields the keys of *rows*; a pipeline returns the hashes it was asked for."""

    async def scan_iter(match=None, count=None):
        for key in rows:
            if scanned is not None:
                scanned.append(key)
            yield key

    def pipeline():
        queued: list = []
        pipe = MagicMock()
        pipe.hgetall.side_effect = queued.append
        pipe.execute = AsyncMock(side_effect=lambda: [rows[k] for k in queued])
        return pipe

    client = MagicMock()
    client.scan_iter = scan_iter
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
