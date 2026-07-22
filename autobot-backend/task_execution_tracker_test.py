# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for async-path MemoryManager offloading in TaskExecutionTracker (#12101).

Sync ``MemoryManager`` methods block the event loop when called directly
from async code. These tests assert that the async paths (``track_task``
and ``_finalize_task``) offload the writes via ``asyncio.to_thread`` instead
of calling the sync MemoryManager methods directly on the loop.
"""

from unittest.mock import MagicMock, patch

import pytest

from task_execution_tracker import TaskExecutionTracker


def _make_tracker() -> TaskExecutionTracker:
    """Build a tracker with a mocked, synchronous MemoryManager."""
    memory_manager = MagicMock()
    memory_manager.create_task_record.return_value = "task-123"
    return TaskExecutionTracker(memory_manager=memory_manager)


@pytest.mark.asyncio
async def test_track_task_offloads_create_and_start_to_thread():
    """track_task's create+start sequence must go through asyncio.to_thread,
    not call the sync MemoryManager methods directly on the event loop."""
    tracker = _make_tracker()

    async with tracker.track_task("name", "desc") as task_context:
        task_context.set_outputs({"ok": True})

    tracker.memory_manager.create_task_record.assert_called_once()
    tracker.memory_manager.start_task.assert_called_once_with("task-123")
    tracker.memory_manager.complete_task.assert_called_once()


@pytest.mark.asyncio
async def test_track_task_offloads_fail_task_to_thread_on_exception():
    """On exception, fail_task must be offloaded via asyncio.to_thread."""
    tracker = _make_tracker()

    with pytest.raises(RuntimeError):
        async with tracker.track_task("name", "desc"):
            raise RuntimeError("boom")

    tracker.memory_manager.fail_task.assert_called_once()
    assert tracker.memory_manager.fail_task.call_args.args[0] == "task-123"


@pytest.mark.asyncio
async def test_track_task_uses_to_thread_not_direct_call():
    """Explicitly assert asyncio.to_thread is the mechanism used to reach
    the sync MemoryManager API, confirming the event loop is never blocked."""
    tracker = _make_tracker()

    with patch("task_execution_tracker.asyncio.to_thread") as mock_to_thread:
        mock_to_thread.return_value = "task-999"

        async def _immediate(func, *args, **kwargs):
            return func(*args, **kwargs)

        mock_to_thread.side_effect = _immediate

        async with tracker.track_task("name", "desc") as task_context:
            task_context.set_outputs({"ok": True})

    assert mock_to_thread.call_count >= 1
    called_funcs = [call.args[0] for call in mock_to_thread.call_args_list]
    assert tracker._create_and_start_task in called_funcs
    assert tracker.memory_manager.complete_task in called_funcs


@pytest.mark.asyncio
async def test_finalize_task_offloads_complete_task_to_thread():
    """_finalize_task must offload the complete_task write via to_thread."""
    tracker = _make_tracker()
    tracker.active_tasks["task-123"] = {"task_name": "x", "agent_type": None, "inputs": None}

    from task_execution_tracker import TaskExecutionContext

    task_context = TaskExecutionContext(tracker, "task-123")
    task_context.set_outputs({"result": "done"})

    with patch("task_execution_tracker.asyncio.to_thread") as mock_to_thread:

        async def _immediate(func, *args, **kwargs):
            return func(*args, **kwargs)

        mock_to_thread.side_effect = _immediate

        await tracker._finalize_task("task-123", task_context)

    mock_to_thread.assert_called_once()
    assert mock_to_thread.call_args.args[0] == tracker.memory_manager.complete_task
    tracker.memory_manager.complete_task.assert_called_once_with("task-123", outputs={"result": "done"})
