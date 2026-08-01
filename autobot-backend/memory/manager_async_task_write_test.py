# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the MemoryManager async task-write variants (#12185).

The sync task-write methods perform blocking SQLite I/O. The async variants
(``acreate_task_record`` / ``astart_task`` / ``acomplete_task`` /
``afail_task``) own the ``asyncio.to_thread`` offload internally so async
callers never block the event loop and can't forget the offload. These tests
verify each variant offloads to and delegates to its sync counterpart with the
forwarded arguments — without touching the database (``__new__`` bypasses
``__init__``; the sync methods are stubbed and executed through the real
``asyncio.to_thread``).
"""

from unittest.mock import MagicMock

import pytest

from memory.manager import MemoryManager


def _manager_with_stubbed_sync_writes() -> MemoryManager:
    mgr = MemoryManager.__new__(MemoryManager)  # bypass __init__ (no DB)
    mgr.create_task_record = MagicMock(return_value="tid")
    mgr.start_task = MagicMock(return_value=True)
    mgr.complete_task = MagicMock(return_value=True)
    mgr.fail_task = MagicMock(return_value=True)
    return mgr


@pytest.mark.asyncio
async def test_acreate_task_record_offloads_and_delegates():
    mgr = _manager_with_stubbed_sync_writes()
    task_id = await mgr.acreate_task_record("name", "desc", agent_type="a")
    assert task_id == "tid"
    mgr.create_task_record.assert_called_once()
    args = mgr.create_task_record.call_args.args
    assert args[0] == "name" and args[1] == "desc"


@pytest.mark.asyncio
async def test_astart_task_offloads_and_delegates():
    mgr = _manager_with_stubbed_sync_writes()
    assert await mgr.astart_task("tid") is True
    mgr.start_task.assert_called_once_with("tid")


@pytest.mark.asyncio
async def test_acomplete_task_offloads_and_delegates():
    mgr = _manager_with_stubbed_sync_writes()
    assert await mgr.acomplete_task("tid", outputs={"x": 1}) is True
    mgr.complete_task.assert_called_once_with("tid", {"x": 1}, None)


@pytest.mark.asyncio
async def test_afail_task_offloads_and_delegates():
    mgr = _manager_with_stubbed_sync_writes()
    assert await mgr.afail_task("tid", "boom") is True
    mgr.fail_task.assert_called_once_with("tid", "boom", 0)
