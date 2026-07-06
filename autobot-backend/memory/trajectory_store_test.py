# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for TrajectoryStore (GH#7357).

Tests cover:
- capture: stores correctly, validates inputs, returns trajectory_id
- find_similar_trajectories: roundtrip via mocked ChromaDB, min_reward filtering
- reward_from_execution: implicit signal derivation
- Acceptance criterion: insert 10 trajectories, query → all 10 returned ranked
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from memory.trajectory_store import (
    TrajectoryStore,
    _hash_start_state,
    get_trajectory_store,
    reward_from_execution,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ACTIONS = [{"agent": "agent_a", "action": "do_something", "params": {}}]


def _make_collection(stored: List[Dict[str, Any]] | None = None) -> MagicMock:
    """Mock AsyncChromaCollection pre-wired with stored trajectories."""
    if stored is None:
        stored = []

    collection = MagicMock()
    collection.add = AsyncMock()

    async def _query(
        query_texts=None,
        n_results=10,
        where=None,
        include=None,
    ):
        limit = min(n_results, len(stored))
        items = stored[:limit]
        return {
            "ids": [[i["id"] for i in items]],
            "documents": [[i["task_text"] for i in items]],
            "metadatas": [[i["metadata"] for i in items]],
            "distances": [[0.05 * idx for idx in range(len(items))]],
        }

    collection.query = _query
    return collection


def _store_entry(
    idx: int,
    task_text: str = "task text",
    reward: float = 1.0,
    outcome: str = "success",
) -> Dict[str, Any]:
    return {
        "id": f"traj_{idx:04d}",
        "task_text": task_text,
        "metadata": {
            "start_state_hash": "",
            "action_sequence_json": json.dumps(_ACTIONS),
            "outcome": outcome,
            "reward": reward,
            "duration": 10.0,
            "agent_id": "agent_a",
            "plan_id": f"plan-{idx}",
            "strategy": "sequential",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        },
    }


async def _store_with_collection(col: MagicMock) -> TrajectoryStore:
    store = TrajectoryStore()
    store._collection = col
    return store


# ---------------------------------------------------------------------------
# Tests: reward_from_execution
# ---------------------------------------------------------------------------


def test_reward_from_execution_success_no_retry():
    assert reward_from_execution({"success": True}) == 1.0


def test_reward_from_execution_success_with_retry():
    assert reward_from_execution({"success": True, "retry_count": 2}) == 0.8


def test_reward_from_execution_failure_partial():
    assert reward_from_execution({"success": False, "criteria_evaluation": {"overall": "partial"}}) == 0.5


def test_reward_from_execution_failure():
    assert reward_from_execution({"success": False}) == 0.0


# ---------------------------------------------------------------------------
# Tests: _hash_start_state
# ---------------------------------------------------------------------------


def test_hash_start_state_none():
    assert _hash_start_state(None) == ""


def test_hash_start_state_empty_dict():
    assert _hash_start_state({}) == ""


def test_hash_start_state_deterministic():
    state = {"key": "value", "count": 1}
    h1 = _hash_start_state(state)
    h2 = _hash_start_state(state)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_hash_start_state_order_independent():
    h1 = _hash_start_state({"a": 1, "b": 2})
    h2 = _hash_start_state({"b": 2, "a": 1})
    assert h1 == h2


# ---------------------------------------------------------------------------
# Tests: capture
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_returns_trajectory_id():
    col = _make_collection()
    store = await _store_with_collection(col)

    traj_id = await store.capture(
        task_text="Deploy service to staging",
        action_sequence=_ACTIONS,
        outcome="success",
        reward=1.0,
        duration=5.0,
        agent_id="deploy_agent",
        plan_id="plan-001",
        strategy="sequential",
    )

    assert traj_id.startswith("traj_")
    col.add.assert_called_once()


@pytest.mark.asyncio
async def test_capture_stores_correct_metadata():
    col = _make_collection()
    store = await _store_with_collection(col)

    await store.capture(
        task_text="Analyze logs",
        action_sequence=_ACTIONS,
        outcome="partial",
        reward=0.5,
        duration=3.2,
        agent_id="analyst",
        plan_id="plan-002",
        strategy="parallel",
        start_state={"server": "up"},
    )

    call_kwargs = col.add.call_args.kwargs
    assert call_kwargs["documents"] == ["Analyze logs"]
    meta = call_kwargs["metadatas"][0]
    assert meta["outcome"] == "partial"
    assert meta["reward"] == 0.5
    assert meta["agent_id"] == "analyst"
    assert meta["plan_id"] == "plan-002"
    assert meta["strategy"] == "parallel"
    assert len(meta["start_state_hash"]) == 64


@pytest.mark.asyncio
async def test_capture_empty_task_text_raises():
    col = _make_collection()
    store = await _store_with_collection(col)

    with pytest.raises(ValueError, match="task_text"):
        await store.capture(
            task_text="",
            action_sequence=_ACTIONS,
            outcome="success",
            reward=1.0,
            duration=1.0,
        )


@pytest.mark.asyncio
async def test_capture_invalid_reward_raises():
    col = _make_collection()
    store = await _store_with_collection(col)

    with pytest.raises(ValueError, match="reward"):
        await store.capture(
            task_text="task",
            action_sequence=_ACTIONS,
            outcome="success",
            reward=1.5,
            duration=1.0,
        )


@pytest.mark.asyncio
async def test_capture_invalid_outcome_raises():
    col = _make_collection()
    store = await _store_with_collection(col)

    with pytest.raises(ValueError, match="outcome"):
        await store.capture(
            task_text="task",
            action_sequence=_ACTIONS,
            outcome="unknown",
            reward=1.0,
            duration=1.0,
        )


# ---------------------------------------------------------------------------
# Tests: find_similar_trajectories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_similar_returns_results():
    stored = [_store_entry(i, reward=1.0) for i in range(3)]
    col = _make_collection(stored)
    store = await _store_with_collection(col)

    results = await store.find_similar_trajectories("task text", top_k=3, min_reward=0.0)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_find_similar_filters_by_min_reward():
    stored = [
        _store_entry(0, reward=1.0),
        _store_entry(1, reward=0.5),
        _store_entry(2, reward=0.3),
    ]
    col = _make_collection(stored)
    store = await _store_with_collection(col)

    results = await store.find_similar_trajectories("task text", top_k=5, min_reward=0.6)
    assert all(r["reward"] >= 0.6 for r in results)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_find_similar_empty_query_returns_empty():
    store = TrajectoryStore()
    results = await store.find_similar_trajectories("", top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_find_similar_result_shape():
    stored = [_store_entry(0)]
    col = _make_collection(stored)
    store = await _store_with_collection(col)

    results = await store.find_similar_trajectories("task", top_k=1, min_reward=0.0)
    assert len(results) == 1
    r = results[0]
    assert "trajectory_id" in r
    assert "task_text" in r
    assert "similarity" in r
    assert "action_sequence" in r
    assert "reward" in r
    assert "outcome" in r


@pytest.mark.asyncio
async def test_find_similar_similarity_order():
    """Lower distance → higher similarity; results stay in distance order."""
    stored = [_store_entry(i, reward=1.0) for i in range(3)]
    col = _make_collection(stored)
    store = await _store_with_collection(col)

    results = await store.find_similar_trajectories("task", top_k=3, min_reward=0.0)
    similarities = [r["similarity"] for r in results]
    assert similarities == sorted(similarities, reverse=True)


@pytest.mark.asyncio
async def test_find_similar_top_k_respected():
    stored = [_store_entry(i, reward=1.0) for i in range(5)]
    col = _make_collection(stored)
    store = await _store_with_collection(col)

    results = await store.find_similar_trajectories("task", top_k=2, min_reward=0.0)
    assert len(results) <= 2


@pytest.mark.asyncio
async def test_find_similar_invalid_top_k_raises():
    store = TrajectoryStore()
    store._collection = MagicMock()
    with pytest.raises(ValueError, match="top_k"):
        await store.find_similar_trajectories("task", top_k=0)


# ---------------------------------------------------------------------------
# Acceptance criterion: insert 10 trajectories, query → all 10 returned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieval_10_trajectories_for_similar_task():
    """Insert 10 successful trajectories for task A; query with similar A' → all 10 returned."""
    stored = [_store_entry(i, task_text="Deploy service X to staging", reward=1.0) for i in range(10)]
    col = _make_collection(stored)
    store = await _store_with_collection(col)

    results = await store.find_similar_trajectories(
        task_text="Deploy service X to staging environment",
        top_k=10,
        min_reward=0.7,
    )

    assert len(results) == 10
    assert all(r["reward"] >= 0.7 for r in results)
    assert all(r["outcome"] == "success" for r in results)


# ---------------------------------------------------------------------------
# Tests: get_trajectory_store singleton
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_trajectory_store_returns_singleton():
    import memory.trajectory_store as _mod

    original = _mod._store
    try:
        _mod._store = None
        s1 = await get_trajectory_store()
        s2 = await get_trajectory_store()
        assert s1 is s2
    finally:
        _mod._store = original


# ---------------------------------------------------------------------------
# Tests: tenant isolation (#11015)
# ---------------------------------------------------------------------------


def _store_entry_tenant(idx: int, tenant_id: str, reward: float = 1.0) -> Dict[str, Any]:
    entry = _store_entry(idx, task_text=f"task {idx}", reward=reward)
    entry["metadata"]["tenant_id"] = tenant_id
    entry["metadata"]["user_id"] = f"user-{idx}"
    return entry


@pytest.mark.asyncio
async def test_capture_tags_tenant_and_user():
    """capture() records tenant_id/user_id in metadata for later scoped retrieval."""
    col = _make_collection()
    store = await _store_with_collection(col)

    await store.capture(
        task_text="Deploy service",
        action_sequence=_ACTIONS,
        outcome="success",
        reward=1.0,
        duration=5.0,
        tenant_id="org-A",
        user_id="user-1",
    )

    _, kwargs = col.add.call_args
    meta = kwargs["metadatas"][0]
    assert meta["tenant_id"] == "org-A"
    assert meta["user_id"] == "user-1"


@pytest.mark.asyncio
async def test_find_similar_scoped_to_tenant_excludes_other_tenants():
    """A tenant-scoped query never returns another tenant's trajectory (#11015)."""
    stored = [
        _store_entry_tenant(0, "org-A"),
        _store_entry_tenant(1, "org-B"),
        _store_entry_tenant(2, "org-A"),
    ]
    col = _make_collection(stored)
    store = await _store_with_collection(col)

    results = await store.find_similar_trajectories("task", top_k=10, min_reward=0.0, tenant_id="org-A")

    assert results, "expected org-A matches"
    assert all(r["trajectory_id"] in {"traj_0000", "traj_0002"} for r in results)
    assert all("org-B" not in r["task_text"] for r in results)


@pytest.mark.asyncio
async def test_find_similar_passes_where_filter_to_chromadb():
    """The tenant is pushed down as a ChromaDB `where` filter (primary guard)."""
    seen = {}
    col = _make_collection([_store_entry_tenant(0, "org-A")])
    orig = col.query

    async def _spy(**kwargs):
        seen.update(kwargs)
        return await orig(**kwargs)

    col.query = _spy
    store = await _store_with_collection(col)

    await store.find_similar_trajectories("task", tenant_id="org-A")
    assert seen.get("where") == {"tenant_id": "org-A"}


@pytest.mark.asyncio
async def test_find_similar_unscoped_returns_all_and_no_where():
    """No tenant_id → unchanged behaviour: no `where` filter, all tenants visible."""
    seen = {}
    stored = [_store_entry_tenant(0, "org-A"), _store_entry_tenant(1, "org-B")]
    col = _make_collection(stored)
    orig = col.query

    async def _spy(**kwargs):
        seen.update(kwargs)
        return await orig(**kwargs)

    col.query = _spy
    store = await _store_with_collection(col)

    results = await store.find_similar_trajectories("task", top_k=10, min_reward=0.0)
    assert "where" not in seen or seen.get("where") is None
    assert len(results) == 2
