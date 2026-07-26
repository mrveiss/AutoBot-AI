# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for A3 (#12554) — memory.consolidate_facts decay/prune.

Asserts the no-data-loss invariant (owned/verified/pinned/recalled/new/high-quality
facts are never pruned), that dry-run deletes nothing, and that enforcing mode
deletes only facts meeting ALL prune conditions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge.facts import FactsMixin, _fact_is_protected

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
OLD = (NOW - timedelta(days=200)).isoformat()
RECENT = (NOW - timedelta(days=5)).isoformat()


def _fact(fid, *, quality=0.0, access=0, ts=OLD, **meta):
    m = {"quality_score": quality, "access_count": access, "timestamp": ts}
    m.update(meta)
    return {"fact_id": fid, "content": f"c-{fid}", "metadata": m, "timestamp": ts}


class _KB(FactsMixin):
    def __init__(self, facts):
        self._facts = facts
        self.ensure_initialized = MagicMock()
        self.get_all_facts = AsyncMock(return_value=facts)
        self.delete_fact = AsyncMock(return_value={"status": "success"})
        self._schedule_bm25_refresh = MagicMock()


# ---- protection predicate --------------------------------------------------


@pytest.mark.parametrize(
    "meta",
    [
        {"important": True},
        {"preserve": True},
        {"pinned": True},
        {"owner_id": "u1"},
        {"user_id": "u1"},
        {"verification_status": "verified"},
    ],
)
def test_protected_facts_recognised(meta):
    assert _fact_is_protected(meta) is True


def test_unprotected_fact():
    assert _fact_is_protected({"quality_score": 0.0}) is False


# ---- candidate collection --------------------------------------------------


def test_only_dead_facts_are_candidates():
    kb = _KB([])
    cutoff = NOW - timedelta(days=180)
    facts = [
        _fact("dead", quality=0.0, access=0, ts=OLD),           # prunable
        _fact("recalled", quality=0.0, access=3, ts=OLD),        # accessed -> keep
        _fact("quality", quality=0.9, access=0, ts=OLD),         # high quality -> keep
        _fact("new", quality=0.0, access=0, ts=RECENT),          # too new -> keep
        _fact("owned", quality=0.0, access=0, ts=OLD, owner_id="u1"),  # owned -> keep
        _fact("noage", quality=0.0, access=0, ts=""),            # unknown age -> keep
    ]
    ids = kb._collect_prune_candidates(facts, quality_floor=0.1, cutoff=cutoff)
    assert ids == ["dead"]


# ---- consolidate_facts orchestration ---------------------------------------


@pytest.mark.asyncio
async def test_dry_run_deletes_nothing():
    facts = [_fact("dead", quality=0.0, access=0, ts=OLD)]
    kb = _KB(facts)
    summary = await kb.consolidate_facts(dry_run=True, now=NOW)
    kb.delete_fact.assert_not_awaited()
    assert summary["candidates"] == 1
    assert summary["pruned"] == 0
    assert summary["dry_run"] is True


@pytest.mark.asyncio
async def test_enforce_deletes_only_dead_facts():
    facts = [
        _fact("dead", quality=0.0, access=0, ts=OLD),
        _fact("owned", quality=0.0, access=0, ts=OLD, owner_id="u1"),
        _fact("recalled", quality=0.0, access=9, ts=OLD),
    ]
    kb = _KB(facts)
    summary = await kb.consolidate_facts(dry_run=False, now=NOW)
    kb.delete_fact.assert_awaited_once_with("dead", _skip_bm25_refresh=True)
    assert summary["pruned"] == 1
    assert summary["remaining"] == 2
    kb._schedule_bm25_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_scan_failure_returns_empty_summary():
    kb = _KB([])
    kb.get_all_facts = AsyncMock(side_effect=RuntimeError("redis down"))
    summary = await kb.consolidate_facts(dry_run=False, now=NOW)
    assert summary == {"scanned": 0, "candidates": 0, "pruned": 0, "remaining": 0, "dry_run": False}
    kb.delete_fact.assert_not_awaited()
