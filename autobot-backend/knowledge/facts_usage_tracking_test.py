# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for A1 (#12552) — fact usage tracking.

Covers:
  - ``access_count`` / ``last_accessed`` surfaced from the Redis hash into the
    returned metadata on read (new facts default cleanly to 0 / "");
  - ``_bump_fact_access`` atomically increments the counter and stamps the time
    for existing facts, and skips missing ones (no resurrection);
  - ``record_fact_access`` is a no-op on empty input and never raises into the
    caller even when Redis blows up (fire-and-forget contract).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from knowledge.facts import FactsMixin, _apply_usage_fields


class _KB(FactsMixin):
    """Minimal FactsMixin host with just the Redis collaborator under test."""

    def __init__(self):
        self.redis_client = MagicMock()


def test_apply_usage_fields_surfaces_counters():
    meta: dict = {}
    _apply_usage_fields({"access_count": "7", "last_accessed": "2026-07-26T00:00:00+00:00"}, meta)
    assert meta["access_count"] == 7
    assert meta["last_accessed"] == "2026-07-26T00:00:00+00:00"


def test_apply_usage_fields_defaults_when_absent():
    meta: dict = {}
    _apply_usage_fields({}, meta)
    assert meta["access_count"] == 0
    assert meta["last_accessed"] == ""


def test_apply_usage_fields_tolerates_garbage():
    meta: dict = {}
    _apply_usage_fields({"access_count": "not-a-number"}, meta)
    assert meta["access_count"] == 0


def test_get_fact_surfaces_usage_fields():
    kb = _KB()
    kb.redis_client.hgetall.return_value = {
        b"content": b"the sky is blue",
        b"metadata": b'{"quality_score": 0.9, "category": "fact"}',
        b"timestamp": b"2026-07-01T00:00:00+00:00",
        b"access_count": b"3",
        b"last_accessed": b"2026-07-25T00:00:00+00:00",
    }
    fact = kb.get_fact("fact-1")
    assert fact is not None
    assert fact["metadata"]["access_count"] == 3
    assert fact["metadata"]["last_accessed"] == "2026-07-25T00:00:00+00:00"
    # existing metadata preserved
    assert fact["metadata"]["quality_score"] == 0.9


def test_get_fact_defaults_usage_when_never_accessed():
    kb = _KB()
    kb.redis_client.hgetall.return_value = {
        b"content": b"new fact",
        b"metadata": b"{}",
        b"timestamp": b"2026-07-01T00:00:00+00:00",
    }
    fact = kb.get_fact("fact-2")
    assert fact["metadata"]["access_count"] == 0
    assert fact["metadata"]["last_accessed"] == ""


@pytest.mark.asyncio
async def test_bump_increments_and_stamps_existing_fact():
    kb = _KB()
    kb.redis_client.exists.return_value = 1
    await kb._bump_fact_access(["fact-1"])
    kb.redis_client.hincrby.assert_called_once_with("fact:fact-1", "access_count", 1)
    # last_accessed stamped with an ISO timestamp
    hset_call = kb.redis_client.hset.call_args
    assert hset_call.args[0] == "fact:fact-1"
    assert hset_call.args[1] == "last_accessed"
    assert "T" in hset_call.args[2]


@pytest.mark.asyncio
async def test_bump_skips_missing_fact():
    kb = _KB()
    kb.redis_client.exists.return_value = 0
    await kb._bump_fact_access(["ghost"])
    kb.redis_client.hincrby.assert_not_called()
    kb.redis_client.hset.assert_not_called()


@pytest.mark.asyncio
async def test_bump_counts_each_fact_once():
    kb = _KB()
    kb.redis_client.exists.return_value = 1
    await kb._bump_fact_access(["a", "b", "c"])
    assert kb.redis_client.hincrby.call_count == 3


@pytest.mark.asyncio
async def test_record_fact_access_noop_on_empty():
    kb = _KB()
    await kb.record_fact_access([])
    kb.redis_client.hincrby.assert_not_called()


@pytest.mark.asyncio
async def test_record_fact_access_never_raises():
    kb = _KB()
    kb.redis_client.exists.side_effect = RuntimeError("redis down")
    # Must not propagate — reinforcement is best-effort.
    await kb.record_fact_access(["fact-1"])
    # allow the scheduled background task to run to completion
    import asyncio

    for _ in range(5):
        await asyncio.sleep(0)
