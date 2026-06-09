# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Integration tests for the unified progress tracker (#6506, Phase 2 of #6495).

These tests cover the contract between ``OperationProgressTracker`` (the
façade in ``utils/long_running_operations/progress_tracker.py``) and
``TaskExecutionTracker`` (the canonical broadcaster in
``task_execution_tracker.py``):

1. ``TaskExecutionTracker.update_progress`` writes the latest snapshot to
   ``operation:{task_id}:progress`` and publishes on both the per-task and
   global channels with the documented wire format.
2. ``TaskExecutionTracker.get_progress`` round-trips the snapshot.
3. ``OperationProgressTracker.update_progress`` updates the in-memory
   ``LongRunningOperation``, fires in-process subscribers, and delegates
   storage / broadcast to ``TaskExecutionTracker`` (no direct Redis access).
4. ``OperationProgressTracker.get_cached_progress`` returns ``None`` (the
   in-memory cache was removed in #6506) and ``get_progress`` round-trips
   through the canonical store.

All Redis access is mocked — no real broker required.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from tests.fixtures.mocks import make_stateful_redis

# ---------------------------------------------------------------------------
# TaskExecutionTracker.update_progress / get_progress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_progress_writes_snapshot_and_publishes_both_channels():
    """``update_progress`` SETs the snapshot and PUBLISHes per-task + global."""
    import task_execution_tracker as tet

    tracker = tet.TaskExecutionTracker(memory_manager=AsyncMock())
    fake_redis = make_stateful_redis()

    with patch.object(tet, "get_async_redis_client", AsyncMock(return_value=fake_redis)):
        await tracker.update_progress(
            task_id="task-abc",
            progress_percent=42.5,
            current_step="Halfway",
            items_processed=5,
            total_items=10,
            operation_type="codebase_indexing",
            name="Index repo X",
            status="running",
        )

    # SET to the per-task key
    assert "operation:task-abc:progress" in fake_redis._store
    payload = json.loads(fake_redis._store["operation:task-abc:progress"])
    assert payload["type"] == "operation_progress"
    assert payload["operation_id"] == "task-abc"
    assert payload["operation_type"] == "codebase_indexing"
    assert payload["name"] == "Index repo X"
    assert payload["status"] == "running"
    assert payload["progress"]["progress_percent"] == 42.5
    assert payload["progress"]["current_step"] == "Halfway"
    assert payload["progress"]["items_processed"] == 5
    assert payload["progress"]["total_items"] == 10
    assert "last_update" in payload["progress"]

    # PUBLISH to per-task + global channels with identical payloads
    channels = [c for c, _ in fake_redis._published]
    assert "operation:task-abc:progress" in channels
    assert "operations:progress" in channels
    assert len(fake_redis._published) == 2
    for _, message in fake_redis._published:
        assert json.loads(message)["operation_id"] == "task-abc"


@pytest.mark.asyncio
async def test_update_progress_swallows_redis_errors():
    """A Redis failure must not raise — only log a warning."""
    import task_execution_tracker as tet

    tracker = tet.TaskExecutionTracker(memory_manager=AsyncMock())

    fake_redis = AsyncMock()
    fake_redis.set.side_effect = RuntimeError("redis down")
    fake_redis.publish.side_effect = RuntimeError("redis down")

    with patch.object(tet, "get_async_redis_client", AsyncMock(return_value=fake_redis)):
        await tracker.update_progress(task_id="task-z", progress_percent=10.0)


@pytest.mark.asyncio
async def test_update_progress_noops_when_redis_unavailable():
    """When ``get_async_redis_client`` returns ``None``, no error and no work."""
    import task_execution_tracker as tet

    tracker = tet.TaskExecutionTracker(memory_manager=AsyncMock())

    with patch.object(tet, "get_async_redis_client", AsyncMock(return_value=None)):
        await tracker.update_progress(task_id="task-y", progress_percent=10.0)


@pytest.mark.asyncio
async def test_get_progress_round_trips_snapshot():
    """``get_progress`` returns the JSON last written by ``update_progress``."""
    import task_execution_tracker as tet

    tracker = tet.TaskExecutionTracker(memory_manager=AsyncMock())
    fake_redis = make_stateful_redis()

    with patch.object(tet, "get_async_redis_client", AsyncMock(return_value=fake_redis)):
        await tracker.update_progress(task_id="task-rt", progress_percent=75.0, current_step="Almost done")
        snapshot = await tracker.get_progress("task-rt")

    assert snapshot is not None
    assert snapshot["operation_id"] == "task-rt"
    assert snapshot["progress"]["progress_percent"] == 75.0
    assert snapshot["progress"]["current_step"] == "Almost done"


@pytest.mark.asyncio
async def test_get_progress_returns_none_when_missing():
    """``get_progress`` returns ``None`` when the key has no value."""
    import task_execution_tracker as tet

    tracker = tet.TaskExecutionTracker(memory_manager=AsyncMock())
    fake_redis = make_stateful_redis()

    with patch.object(tet, "get_async_redis_client", AsyncMock(return_value=fake_redis)):
        snapshot = await tracker.get_progress("task-missing")

    assert snapshot is None


# ---------------------------------------------------------------------------
# OperationProgressTracker façade
# ---------------------------------------------------------------------------


def _make_operation(operation_id: str = "op-1"):
    """Build a minimal LongRunningOperation for façade tests."""
    from utils.long_running_operations.types import (
        LongRunningOperation,
        OperationType,
    )

    return LongRunningOperation(
        operation_id=operation_id,
        operation_type=OperationType.CODEBASE_INDEXING,
        name="test op",
        description="test",
    )


@pytest.mark.asyncio
async def test_facade_delegates_to_canonical_tracker():
    """``OperationProgressTracker.update_progress`` delegates storage + broadcast.

    Verifies: in-memory operation fields are updated, in-process subscriber is
    fired, and ``TaskExecutionTracker.update_progress`` is called with the
    matching kwargs (no direct Redis access from the façade).
    """
    from utils.long_running_operations.progress_tracker import OperationProgressTracker

    tracker = OperationProgressTracker()
    operation = _make_operation("op-facade")
    delegated_calls: list = []

    fake_canonical = AsyncMock()

    async def _capture_update_progress(**kwargs):
        delegated_calls.append(kwargs)

    fake_canonical.update_progress.side_effect = _capture_update_progress

    fired_callbacks: list = []

    async def _subscriber(op):
        fired_callbacks.append(op.operation_id)

    await tracker.subscribe_to_progress("op-facade", _subscriber)

    with patch(
        "task_execution_tracker.get_task_tracker",
        lambda: fake_canonical,
    ):
        await tracker.update_progress(
            operation,
            current_step="Phase 1",
            progress_percent=33.3,
            items_processed=3,
            total_items=9,
            details={"note": "first third"},
        )

    # In-memory operation state updated
    assert operation.progress.current_step == "Phase 1"
    assert operation.progress.progress_percent == 33.3
    assert operation.progress.items_processed == 3
    assert operation.progress.total_items == 9
    assert operation.progress.details["note"] == "first third"

    # In-process subscriber fired exactly once
    assert fired_callbacks == ["op-facade"]

    # Delegated to canonical tracker with the right payload
    assert len(delegated_calls) == 1
    call = delegated_calls[0]
    assert call["task_id"] == "op-facade"
    assert call["progress_percent"] == 33.3
    assert call["current_step"] == "Phase 1"
    assert call["items_processed"] == 3
    assert call["total_items"] == 9
    assert call["operation_type"] == "codebase_indexing"
    assert call["name"] == "test op"
    assert call["details"]["note"] == "first third"


def test_get_cached_progress_returns_none_post_6506():
    """The in-memory cache was removed in #6506; the sync method must return None."""
    from utils.long_running_operations.progress_tracker import OperationProgressTracker

    tracker = OperationProgressTracker()
    assert tracker.get_cached_progress("anything") is None


@pytest.mark.asyncio
async def test_facade_get_progress_round_trips_through_canonical():
    """``OperationProgressTracker.get_progress`` reads via the canonical tracker."""
    from utils.long_running_operations.progress_tracker import OperationProgressTracker

    canonical_snapshot = {
        "operation_id": "op-rt",
        "progress": {
            "current_step": "Step",
            "progress_percent": 50.0,
            "items_processed": 5,
            "total_items": 10,
            "estimated_remaining": 12.0,
            "last_update": "2026-04-29T00:00:00+00:00",
            "details": {"k": "v"},
        },
    }

    fake_canonical = AsyncMock()
    fake_canonical.get_progress = AsyncMock(return_value=canonical_snapshot)

    tracker = OperationProgressTracker()
    with patch(
        "task_execution_tracker.get_task_tracker",
        lambda: fake_canonical,
    ):
        result = await tracker.get_progress("op-rt")

    assert result is not None
    assert result["operation_id"] == "op-rt"
    assert result["progress_percent"] == 50.0
    assert result["current_step"] == "Step"
    assert result["details"] == {"k": "v"}
    fake_canonical.get_progress.assert_awaited_once_with("op-rt")


@pytest.mark.asyncio
async def test_facade_clear_progress_drops_subscribers():
    """``clear_progress`` removes in-process subscribers for the given operation."""
    from utils.long_running_operations.progress_tracker import OperationProgressTracker

    tracker = OperationProgressTracker()
    await tracker.subscribe_to_progress("op-clear", lambda _op: None)
    assert "op-clear" in tracker._subscribers

    tracker.clear_progress("op-clear")
    assert "op-clear" not in tracker._subscribers
