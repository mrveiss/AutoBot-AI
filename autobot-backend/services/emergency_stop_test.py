# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for emergency-stop reporting (#16843).

Before this, ``POST /system/emergency-stop`` returned a fixed success string
regardless of what actually happened and never told the takeover manager
which tasks to pause. These assert the three outcomes the report must now
distinguish: nothing running, tasks found and durably paused, and tasks
found but only paused in-process because Redis was unavailable.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.emergency_stop import execute_emergency_stop

pytestmark = pytest.mark.asyncio


def _tracker(active_task_ids):
    tracker = MagicMock()
    tracker.get_active_tasks.return_value = {tid: {} for tid in active_task_ids}
    return tracker


def _manager(request_id="takeover-123", durable=True):
    manager = MagicMock()
    manager.request_takeover = AsyncMock(return_value=request_id)
    manager.is_durable.return_value = durable
    return manager


def _patched(tracker, manager):
    return patch.multiple(
        "services.emergency_stop",
        get_task_tracker=MagicMock(return_value=tracker),
        get_takeover_manager=MagicMock(return_value=manager),
    )


async def test_nothing_running_reports_empty_pause_list():
    manager = _manager()
    with _patched(_tracker([]), manager):
        result = await execute_emergency_stop()

    assert result["tasks_paused"] == []
    assert "no active tasks were running" in result["message"]
    assert manager.request_takeover.call_args.kwargs["affected_tasks"] == []


async def test_active_tasks_are_passed_to_request_takeover():
    manager = _manager()
    with _patched(_tracker(["task-1", "task-2"]), manager):
        result = await execute_emergency_stop()

    assert result["tasks_paused"] == ["task-1", "task-2"]
    assert manager.request_takeover.call_args.kwargs["affected_tasks"] == ["task-1", "task-2"]


async def test_durable_pause_reports_durable_true():
    manager = _manager(durable=True)
    with _patched(_tracker(["task-1"]), manager):
        result = await execute_emergency_stop()

    assert result["durable"] is True
    assert "paused 1 active task" in result["message"]
    assert "IN-MEMORY ONLY" not in result["message"]


async def test_fallback_pause_reports_durable_false_and_warns_in_message():
    manager = _manager(durable=False)
    with _patched(_tracker(["task-1", "task-2"]), manager):
        result = await execute_emergency_stop()

    assert result["durable"] is False
    assert result["tasks_paused"] == ["task-1", "task-2"]
    assert "IN-MEMORY ONLY" in result["message"]


async def test_nothing_running_is_durable_status_regardless_of_the_flag():
    # No tasks to pause means the durability of the (empty) pause is moot --
    # the message must stay the "nothing to stop" branch either way.
    manager = _manager(durable=False)
    with _patched(_tracker([]), manager):
        result = await execute_emergency_stop()

    assert "no active tasks were running" in result["message"]
    assert "IN-MEMORY ONLY" not in result["message"]


async def test_response_always_reports_success_and_the_takeover_request_id():
    manager = _manager(request_id="takeover-xyz")
    with _patched(_tracker([]), manager):
        result = await execute_emergency_stop()

    assert result["success"] is True
    assert result["takeover_request_id"] == "takeover-xyz"


async def test_requesting_agent_is_forwarded():
    manager = _manager()
    with _patched(_tracker([]), manager):
        await execute_emergency_stop(requesting_agent="custom_caller")

    assert manager.request_takeover.call_args.kwargs["requesting_agent"] == "custom_caller"
