# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for async-path MemoryManager offloading in TaskExecutionTracker.

Sync ``MemoryManager`` task-write methods block the event loop when called
directly from async code (#12101). Issue #12185 moved the offload into the
MemoryManager async task-write variants (``acreate_task_record`` /
``astart_task`` / ``acomplete_task`` / ``afail_task``), which own the
``asyncio.to_thread`` hop internally. These tests assert the tracker's async
paths (``track_task`` / ``_finalize_task``) use those async variants and never
call the loop-blocking sync methods directly.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from task_execution_tracker import TaskExecutionContext, TaskExecutionTracker


def _make_tracker() -> TaskExecutionTracker:
    """Build a tracker with a mocked MemoryManager exposing async task-writes."""
    memory_manager = MagicMock()
    memory_manager.acreate_task_record = AsyncMock(return_value="task-123")
    memory_manager.astart_task = AsyncMock(return_value=True)
    memory_manager.acomplete_task = AsyncMock(return_value=True)
    memory_manager.afail_task = AsyncMock(return_value=True)
    return TaskExecutionTracker(memory_manager=memory_manager)


@pytest.mark.asyncio
async def test_track_task_uses_async_task_write_variants():
    """track_task's create+start+complete sequence must go through the async
    task-write variants (which own the offload)."""
    tracker = _make_tracker()

    async with tracker.track_task("name", "desc") as task_context:
        task_context.set_outputs({"ok": True})

    tracker.memory_manager.acreate_task_record.assert_awaited_once()
    tracker.memory_manager.astart_task.assert_awaited_once_with("task-123")
    tracker.memory_manager.acomplete_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_track_task_fails_via_async_variant_on_exception():
    """On exception, afail_task must be awaited."""
    tracker = _make_tracker()

    with pytest.raises(RuntimeError):
        async with tracker.track_task("name", "desc"):
            raise RuntimeError("boom")

    tracker.memory_manager.afail_task.assert_awaited_once()
    assert tracker.memory_manager.afail_task.await_args.args[0] == "task-123"


@pytest.mark.asyncio
async def test_track_task_never_calls_sync_task_writes_directly():
    """The loop-blocking sync task-write methods must never be called directly;
    the async variants are used instead so the event loop is never blocked."""
    tracker = _make_tracker()

    async with tracker.track_task("name", "desc") as task_context:
        task_context.set_outputs({"ok": True})

    tracker.memory_manager.create_task_record.assert_not_called()
    tracker.memory_manager.start_task.assert_not_called()
    tracker.memory_manager.complete_task.assert_not_called()
    tracker.memory_manager.acreate_task_record.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_task_uses_acomplete_task():
    """_finalize_task must await acomplete_task (not the sync complete_task)."""
    tracker = _make_tracker()
    tracker.active_tasks["task-123"] = {"task_name": "x", "agent_type": None, "inputs": None}

    task_context = TaskExecutionContext(tracker, "task-123")
    task_context.set_outputs({"result": "done"})

    await tracker._finalize_task("task-123", task_context)

    tracker.memory_manager.acomplete_task.assert_awaited_once_with("task-123", outputs={"result": "done"})
    tracker.memory_manager.complete_task.assert_not_called()
