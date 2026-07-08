# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Trajectory-store consolidation: dedupe + prune (GH#11263)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from memory import trajectory_store as ts


def _meta(reward, ts_dt, user_id="u1", tenant_id=""):
    return {"reward": reward, "timestamp": ts_dt.isoformat(), "user_id": user_id, "tenant_id": tenant_id}


NOW = datetime(2026, 7, 8, tzinfo=timezone.utc)
RECENT = NOW - timedelta(days=1)
OLD = NOW - timedelta(days=60)


# --- pure helpers ----------------------------------------------------------


def test_dedup_keeps_highest_reward_survivor():
    ids = ["a", "b", "c"]
    docs = ["Deploy X", "deploy x", "Other task"]
    metas = [_meta(0.5, RECENT), _meta(0.9, RECENT), _meta(1.0, RECENT)]
    drop = ts._dedup_delete_ids(ids, docs, metas)
    assert drop == {"a"}  # "b" (0.9) beats "a" (0.5); "c" is unique


def test_dedup_scopes_by_user_and_tenant():
    ids = ["a", "b"]
    docs = ["same task", "same task"]
    metas = [_meta(0.5, RECENT, user_id="u1"), _meta(0.9, RECENT, user_id="u2")]
    assert ts._dedup_delete_ids(ids, docs, metas) == set()  # different users → not duplicates


def test_stale_prunes_only_old_low_reward():
    ids = ["old_low", "old_high", "new_low"]
    metas = [_meta(0.1, OLD), _meta(0.9, OLD), _meta(0.1, RECENT)]
    drop = ts._stale_delete_ids(ids, metas, reward_floor=0.4, cutoff=NOW - timedelta(days=30), skip=set())
    assert drop == {"old_low"}


def test_stale_skips_already_dropped():
    ids = ["x"]
    metas = [_meta(0.1, OLD)]
    drop = ts._stale_delete_ids(ids, metas, reward_floor=0.4, cutoff=NOW, skip={"x"})
    assert drop == set()


# --- consolidate() end to end ---------------------------------------------


@pytest.mark.asyncio
async def test_consolidate_deletes_dupes_and_stale():
    collection = AsyncMock()
    collection.get = AsyncMock(
        return_value={
            "ids": ["a", "b", "stale"],
            "documents": ["task one", "task one", "task two"],
            "metadatas": [_meta(0.9, RECENT), _meta(0.5, RECENT), _meta(0.1, OLD)],
        }
    )
    store = ts.TrajectoryStore()
    store._get_collection = AsyncMock(return_value=collection)

    summary = await store.consolidate(reward_floor=0.4, max_age_days=30, now=NOW)

    assert summary["scanned"] == 3
    assert summary["duplicates_removed"] == 1  # "b"
    assert summary["pruned"] == 1  # "stale"
    assert summary["remaining"] == 1  # "a"
    deleted = set(collection.delete.call_args.kwargs["ids"])
    assert deleted == {"b", "stale"}


@pytest.mark.asyncio
async def test_consolidate_noop_when_empty():
    collection = AsyncMock()
    collection.get = AsyncMock(return_value={"ids": [], "documents": [], "metadatas": []})
    store = ts.TrajectoryStore()
    store._get_collection = AsyncMock(return_value=collection)

    summary = await store.consolidate(now=NOW)

    assert summary == {"scanned": 0, "duplicates_removed": 0, "pruned": 0, "remaining": 0}
    collection.delete.assert_not_called()


@pytest.mark.asyncio
async def test_consolidate_non_fatal_on_read_error():
    collection = AsyncMock()
    collection.get = AsyncMock(side_effect=RuntimeError("chroma down"))
    store = ts.TrajectoryStore()
    store._get_collection = AsyncMock(return_value=collection)

    summary = await store.consolidate(now=NOW)

    assert summary["scanned"] == 0
    collection.delete.assert_not_called()
