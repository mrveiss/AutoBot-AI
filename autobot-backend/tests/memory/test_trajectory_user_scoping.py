# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11089 — trajectory retrieval must isolate by user, not only by tenant.

In single-company deployments ``tenant_id`` is frequently empty/identical across
all users, so tenant-only scoping leaves an intra-tenant cross-user injection
gap. ``find_similar_trajectories`` now also scopes by ``user_id`` (default on via
``AUTOBOT_TRAJECTORY_USER_SCOPED``): the ChromaDB ``where`` filter is the primary
guard and a client-side backstop enforces it again.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import memory.trajectory_store as ts


def _collection_returning(*users: str) -> AsyncMock:
    coll = AsyncMock()
    coll.query = AsyncMock(
        return_value={
            "ids": [[f"t{i}" for i in range(len(users))]],
            "documents": [[f"task from {u}" for u in users]],
            "metadatas": [
                [{"tenant_id": "org1", "user_id": u, "reward": 0.9, "action_sequence_json": "[]"} for u in users]
            ],
            "distances": [[0.1] * len(users)],
        }
    )
    return coll


async def _run(store, coll, **kwargs):
    with patch.object(store, "_get_collection", AsyncMock(return_value=coll)):
        return await store.find_similar_trajectories("task", top_k=5, min_reward=0.5, **kwargs)


@pytest.mark.asyncio
async def test_where_clause_scopes_by_tenant_and_user():
    store = ts.TrajectoryStore()
    coll = _collection_returning("alice")
    with patch.object(ts, "_USER_SCOPED_RETRIEVAL", True):
        await _run(store, coll, tenant_id="org1", user_id="alice")
    where = coll.query.call_args.kwargs.get("where")
    assert where == {"$and": [{"tenant_id": "org1"}, {"user_id": "alice"}]}


@pytest.mark.asyncio
async def test_backstop_drops_other_users_trajectories():
    store = ts.TrajectoryStore()
    coll = _collection_returning("alice", "bob")  # a lenient filter could leak bob
    with patch.object(ts, "_USER_SCOPED_RETRIEVAL", True):
        results = await _run(store, coll, tenant_id="org1", user_id="alice")
    docs = [r["task_text"] for r in results]
    assert docs == ["task from alice"]
    assert "task from bob" not in docs


@pytest.mark.asyncio
async def test_user_only_scope_when_no_tenant():
    store = ts.TrajectoryStore()
    coll = _collection_returning("alice")
    with patch.object(ts, "_USER_SCOPED_RETRIEVAL", True):
        await _run(store, coll, user_id="alice")
    assert coll.query.call_args.kwargs.get("where") == {"user_id": "alice"}


@pytest.mark.asyncio
async def test_flag_disabled_keeps_tenant_only_scope():
    store = ts.TrajectoryStore()
    coll = _collection_returning("alice", "bob")
    with patch.object(ts, "_USER_SCOPED_RETRIEVAL", False):
        results = await _run(store, coll, tenant_id="org1", user_id="alice")
    # With user-scoping off, the org shares learning — no user filter applied.
    assert coll.query.call_args.kwargs.get("where") == {"tenant_id": "org1"}
    assert len(results) == 2
