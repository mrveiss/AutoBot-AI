# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the pending-set reconcile optimization in BackgroundVectorizer (#11296).

The reconciler must:
  - do a full `fact:*` scan on the first cycle and every Nth cycle (safety net),
  - otherwise read ONLY the `kb:vectorize:pending` set (O(pending), not O(N)),
  - early-return without any `fact:*` scan when the pending set is empty on a fast cycle,
  - keep the set tight (SADD to-process, SREM completed / on completion).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from background_vectorization import FULL_SCAN_EVERY_N_CYCLES, PENDING_SET_KEY, BackgroundVectorizer


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _FakePipe:
    def __init__(self):
        self.sadd = AsyncMock()
        self.srem = AsyncMock()
        self.execute = AsyncMock(return_value=[])


def _make_kb(pending_members=None):
    """A kb whose redis() exposes the calls the reconciler makes."""
    redis = MagicMock()
    redis.smembers = AsyncMock(return_value=set(pending_members or []))
    redis.srem = AsyncMock()
    pipe = _FakePipe()

    @asynccontextmanager
    async def _pipeline():
        yield pipe

    redis.pipeline = _pipeline
    kb = MagicMock()
    kb.redis = MagicMock(return_value=redis)
    kb._scan_redis_keys_async = AsyncMock(return_value=[])
    kb._fake_pipe = pipe
    kb._fake_redis = redis
    return kb


def test_fact_id_extraction() -> None:
    assert BackgroundVectorizer._fact_id("fact:abc-123") == "abc-123"
    assert BackgroundVectorizer._fact_id("bare") == "bare"


def test_filter_pending_facts_returns_completed_keys() -> None:
    v = BackgroundVectorizer()
    batch = ["fact:a", "fact:b", "fact:c"]
    status = [b"completed", None, b"failed"]
    to_process, skipped, completed = v._filter_pending_facts(batch, status)
    assert to_process == ["fact:b", "fact:c"]
    assert skipped == 1
    assert completed == ["fact:a"]


def test_first_cycle_does_full_scan() -> None:
    v = BackgroundVectorizer()
    v._process_batch = AsyncMock(
        return_value={"success": 0, "skipped": 0, "failed": 0, "tokens": 0, "processing_time": 0.0}
    )
    kb = _make_kb(pending_members=[])
    _run(v.vectorize_pending_facts(kb))
    assert v._cycle_count == 1
    kb._scan_redis_keys_async.assert_awaited_once()  # full scan seeds the set
    kb._fake_redis.smembers.assert_not_called()


def test_fast_cycle_reads_pending_set_not_full_scan() -> None:
    v = BackgroundVectorizer()
    v._process_batch = AsyncMock(
        return_value={"success": 0, "skipped": 0, "failed": 0, "tokens": 0, "processing_time": 0.0}
    )
    v._cycle_count = 1  # next cycle -> 2, a fast cycle (assuming N>2)
    assert FULL_SCAN_EVERY_N_CYCLES > 2
    kb = _make_kb(pending_members=[b"x"])
    _run(v.vectorize_pending_facts(kb))
    assert v._cycle_count == 2
    kb._fake_redis.smembers.assert_awaited_once_with(PENDING_SET_KEY)
    kb._scan_redis_keys_async.assert_not_called()  # THE win: no O(N) fact:* scan


def test_fast_cycle_empty_pending_is_noop() -> None:
    v = BackgroundVectorizer()
    v._process_batch = AsyncMock()
    v._cycle_count = 1  # -> 2, fast cycle
    kb = _make_kb(pending_members=[])
    _run(v.vectorize_pending_facts(kb))
    kb._scan_redis_keys_async.assert_not_called()
    v._process_batch.assert_not_called()  # nothing pending -> no work


def test_full_scan_recurs_every_n_cycles() -> None:
    v = BackgroundVectorizer()
    v._process_batch = AsyncMock(
        return_value={"success": 0, "skipped": 0, "failed": 0, "tokens": 0, "processing_time": 0.0}
    )
    v._cycle_count = FULL_SCAN_EVERY_N_CYCLES - 1  # -> N, a full-scan cycle
    kb = _make_kb(pending_members=[b"x"])
    _run(v.vectorize_pending_facts(kb))
    kb._scan_redis_keys_async.assert_awaited_once()
    kb._fake_redis.smembers.assert_not_called()


def test_sync_pending_set_sadds_and_srems() -> None:
    v = BackgroundVectorizer()
    kb = _make_kb()
    _run(v._sync_pending_set(kb, to_add=["fact:a", "fact:b"], to_remove=["fact:c"]))
    kb._fake_pipe.sadd.assert_awaited_once_with(PENDING_SET_KEY, "a", "b")
    kb._fake_pipe.srem.assert_awaited_once_with(PENDING_SET_KEY, "c")


def test_scan_pending_set_builds_fact_keys() -> None:
    v = BackgroundVectorizer()
    kb = _make_kb(pending_members=[b"a", b"b"])
    keys = _run(v._scan_pending_set(kb))
    assert sorted(keys) == ["fact:a", "fact:b"]


def test_mark_complete_srems_from_pending_set() -> None:
    v = BackgroundVectorizer()
    kb = _make_kb()
    kb._fake_redis.hset = AsyncMock()
    _run(v._mark_vectorization_complete(kb, "fact:z"))
    kb._fake_redis.srem.assert_awaited_once_with(PENDING_SET_KEY, "z")
