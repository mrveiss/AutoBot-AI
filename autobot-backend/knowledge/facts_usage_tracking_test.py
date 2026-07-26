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

from knowledge.facts import _ACCESS_BUMP_LUA, _ACCESS_TASKS, FactsMixin, _apply_usage_fields


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


def test_process_fact_data_surfaces_usage_fields():
    kb = _KB()
    raw = {
        b"content": b"processed fact",
        b"metadata": b'{"category": "note"}',
        b"timestamp": b"2026-07-01T00:00:00+00:00",
        b"access_count": b"5",
        b"last_accessed": b"2026-07-20T00:00:00+00:00",
    }
    fact = kb._process_fact_data("fact:fact-9", raw)
    assert fact is not None
    assert fact["metadata"]["access_count"] == 5
    assert fact["metadata"]["last_accessed"] == "2026-07-20T00:00:00+00:00"


def test_bump_lua_guards_existence_atomically():
    # The atomic guard against ghost-resurrection lives in the Lua script, not
    # in a TOCTOU exists()->write sequence.
    assert "EXISTS" in _ACCESS_BUMP_LUA
    assert "HINCRBY" in _ACCESS_BUMP_LUA
    assert "HSET" in _ACCESS_BUMP_LUA


@pytest.mark.asyncio
async def test_bump_evals_atomic_script_per_fact():
    kb = _KB()
    await kb._bump_fact_access(["fact-1"])
    call = kb.redis_client.eval.call_args
    assert call.args[0] == _ACCESS_BUMP_LUA
    assert call.args[1] == 1  # numkeys
    assert call.args[2] == "fact:fact-1"
    assert "T" in call.args[3]  # ISO last_accessed stamp


@pytest.mark.asyncio
async def test_bump_counts_each_fact_once():
    kb = _KB()
    await kb._bump_fact_access(["a", "b", "c"])
    assert kb.redis_client.eval.call_count == 3


@pytest.mark.asyncio
async def test_bump_dedups_repeated_ids():
    kb = _KB()
    await kb._bump_fact_access(["a", "a", "b"])
    assert kb.redis_client.eval.call_count == 2


@pytest.mark.asyncio
async def test_record_fact_access_noop_on_empty():
    kb = _KB()
    await kb.record_fact_access([])
    kb.redis_client.hincrby.assert_not_called()


@pytest.mark.asyncio
async def test_record_fact_access_never_raises():
    import asyncio

    kb = _KB()
    kb.redis_client.eval.side_effect = RuntimeError("redis down")
    # Must not propagate — reinforcement is best-effort.
    await kb.record_fact_access(["fact-1"])
    # Deterministically drain the scheduled background task(s).
    if _ACCESS_TASKS:
        await asyncio.gather(*list(_ACCESS_TASKS), return_exceptions=True)
