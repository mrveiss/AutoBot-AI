# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for live mid-task steering (#10543).

Acceptance criteria:
  - Sending a steering message to an in-flight task causes a plan delta in the
    next tool selection context (steering_guidance key present + non-empty).
  - Steering events appear in the trajectory (TaskContext.steering_events).
  - cancel/pause semantics are unchanged by the steering feature.
  - steer() returns False when loop is not RUNNING.
  - _drain_steering_inbox() is non-blocking (no hang when inbox is empty).
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agent_loop.loop as _loop_module
from agent_loop.loop import AgentLoop
from agent_loop.types import AgentLoopConfig, LoopState, SteeringEntry, TaskContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loop(max_iterations: int = 20) -> AgentLoop:
    """Return an AgentLoop wired with mock event stream."""
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    config = AgentLoopConfig(
        max_iterations=max_iterations,
        mandatory_think_enabled=False,
        think_on_completion=False,
        log_iterations=False,
        require_approval_for_sensitive=False,
    )
    loop = AgentLoop(event_stream=event_stream, config=config)
    loop._current_context = TaskContext(task_id="t-steer", description="steer test task")
    loop._state = LoopState.RUNNING
    loop._iteration_count = 2  # simulate mid-task
    return loop


# ---------------------------------------------------------------------------
# steer() gate: returns False when not RUNNING
# ---------------------------------------------------------------------------


class TestSteerGate:
    @pytest.mark.asyncio
    async def test_steer_returns_false_when_idle(self):
        loop = _make_loop()
        loop._state = LoopState.IDLE
        result = await loop.steer("sid-1", "ignore that file")
        assert result is False

    @pytest.mark.asyncio
    async def test_steer_returns_false_when_cancelled(self):
        loop = _make_loop()
        loop._state = LoopState.CANCELLED
        result = await loop.steer("sid-2", "do this instead")
        assert result is False

    @pytest.mark.asyncio
    async def test_steer_returns_true_when_running(self):
        loop = _make_loop()
        result = await loop.steer("sid-3", "focus on module X")
        assert result is True


# ---------------------------------------------------------------------------
# steer() enqueues into steering inbox
# ---------------------------------------------------------------------------


class TestSteerInbox:
    @pytest.mark.asyncio
    async def test_steer_queues_entry(self):
        loop = _make_loop()
        await loop.steer("sid-10", "use the CSV not the JSON")
        assert not loop._steering_inbox.empty()
        entry = loop._steering_inbox.get_nowait()
        assert isinstance(entry, SteeringEntry)
        assert entry.steering_id == "sid-10"
        assert entry.guidance == "use the CSV not the JSON"

    @pytest.mark.asyncio
    async def test_steer_multiple_messages_queued_in_order(self):
        loop = _make_loop()
        await loop.steer("sid-a", "first hint")
        await loop.steer("sid-b", "second hint")
        entries = []
        while not loop._steering_inbox.empty():
            entries.append(loop._steering_inbox.get_nowait())
        assert [e.steering_id for e in entries] == ["sid-a", "sid-b"]


# ---------------------------------------------------------------------------
# _drain_steering_inbox: non-blocking + records in trajectory
# ---------------------------------------------------------------------------


class TestDrainSteeringInbox:
    @pytest.mark.asyncio
    async def test_drain_empty_inbox_returns_empty_list(self):
        loop = _make_loop()
        with patch.object(_loop_module, "_bus_publish_event", new=AsyncMock()):
            drained = await loop._drain_steering_inbox()
        assert drained == []

    @pytest.mark.asyncio
    async def test_drain_records_in_trajectory(self):
        loop = _make_loop()
        await loop.steer("sid-traj", "check the config file first")
        with patch.object(_loop_module, "_bus_publish_event", new=AsyncMock()):
            drained = await loop._drain_steering_inbox()
        assert len(drained) == 1
        assert loop._current_context.steering_events[0].steering_id == "sid-traj"

    @pytest.mark.asyncio
    async def test_drain_publishes_live_event(self):
        loop = _make_loop()
        await loop.steer("sid-pub", "skip the migration step")
        mock_publish = AsyncMock()
        with patch.object(_loop_module, "_bus_publish_event", new=mock_publish):
            await loop._drain_steering_inbox()
        mock_publish.assert_awaited_once()
        call_args = mock_publish.call_args
        # channel is task:{task_id}
        assert call_args[0][0] == "task:t-steer"
        # event type is STEERING_RECEIVED
        from events.event_types import STEERING_RECEIVED
        assert call_args[0][1] == STEERING_RECEIVED
        payload = call_args[0][2]
        assert payload["steering_id"] == "sid-pub"
        assert payload["guidance"] == "skip the migration step"


# ---------------------------------------------------------------------------
# Plan delta: _analyze_events injects steering_guidance into context
# ---------------------------------------------------------------------------


class TestAnalyzeEventsPlanDelta:
    """Asserts that a pending steering message causes a plan delta in the
    events context returned by _analyze_events (#10543 acceptance criterion)."""

    @pytest.mark.asyncio
    async def test_analyze_events_has_steering_guidance_when_steered(self):
        loop = _make_loop()
        await loop.steer("sid-delta", "do not touch auth.py")
        mock_publish = AsyncMock()
        with patch.object(_loop_module, "_bus_publish_event", new=mock_publish):
            context = await loop._analyze_events()
        # Plan delta: steering_guidance present and non-empty
        assert context.get("has_steering") is True
        guidance_list = context.get("steering_guidance", [])
        assert len(guidance_list) == 1
        assert guidance_list[0]["steering_id"] == "sid-delta"
        assert guidance_list[0]["guidance"] == "do not touch auth.py"

    @pytest.mark.asyncio
    async def test_analyze_events_no_steering_key_when_inbox_empty(self):
        loop = _make_loop()
        mock_publish = AsyncMock()
        with patch.object(_loop_module, "_bus_publish_event", new=mock_publish):
            context = await loop._analyze_events()
        assert "has_steering" not in context
        assert "steering_guidance" not in context

    @pytest.mark.asyncio
    async def test_analyze_events_multiple_guidance_entries(self):
        loop = _make_loop()
        await loop.steer("sid-m1", "hint one")
        await loop.steer("sid-m2", "hint two")
        with patch.object(_loop_module, "_bus_publish_event", new=AsyncMock()):
            context = await loop._analyze_events()
        assert context["has_steering"] is True
        assert len(context["steering_guidance"]) == 2


# ---------------------------------------------------------------------------
# cancel/pause semantics unchanged
# ---------------------------------------------------------------------------


class TestCancelPauseUnchanged:
    @pytest.mark.asyncio
    async def test_cancel_sets_state_cancelled(self):
        loop = _make_loop()
        await loop.cancel()
        assert loop._state == LoopState.CANCELLED

    @pytest.mark.asyncio
    async def test_pause_sets_state_paused(self):
        loop = _make_loop()
        await loop.pause()
        assert loop._state == LoopState.PAUSED

    @pytest.mark.asyncio
    async def test_steer_does_not_affect_cancel(self):
        loop = _make_loop()
        await loop.steer("sid-x", "do something else")
        await loop.cancel()
        # State is CANCELLED; steer queue has a message but that's fine —
        # loop exits and drains nothing.
        assert loop._state == LoopState.CANCELLED

    @pytest.mark.asyncio
    async def test_steering_inbox_cleared_on_task_reinit(self):
        loop = _make_loop()
        await loop.steer("sid-old", "stale message")
        # Simulate starting a new task (re-init context)
        loop._init_task_context("t-new", "new task", None)
        assert loop._steering_inbox.empty()


# ---------------------------------------------------------------------------
# SteeringEntry.to_dict round-trip
# ---------------------------------------------------------------------------


class TestSteeringEntryDict:
    def test_to_dict_keys(self):
        entry = SteeringEntry(steering_id="sid-rt", guidance="recheck line 42", iteration=5)
        d = entry.to_dict()
        assert d["steering_id"] == "sid-rt"
        assert d["guidance"] == "recheck line 42"
        assert d["iteration"] == 5
        assert "timestamp" in d
