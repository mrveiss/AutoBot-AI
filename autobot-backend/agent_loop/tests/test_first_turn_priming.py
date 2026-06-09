# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for first_turn_note injection into LLM message context.

Covers issue #4563 / feature #4528:
  1. Injection on turn 1 — note appended to task_description when enabled.
  2. Disabled guard — note NOT injected when first_turn_priming_enabled=False.
  3. Single-use — first_turn_note popped; absent on turn 2+.
  4. Empty note guard — empty string NOT appended.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_loop.loop import AgentLoop
from agent_loop.types import AgentLoopConfig, IterationResult, LoopState, TaskContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loop(first_turn_priming_enabled: bool = True) -> AgentLoop:
    """Return an AgentLoop with a minimal mock event_stream."""
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    config = AgentLoopConfig(
        first_turn_priming_enabled=first_turn_priming_enabled,
        max_iterations=5,
        think_on_completion=False,
        mandatory_think_enabled=False,
        log_iterations=False,
    )
    loop = AgentLoop(event_stream=event_stream, config=config)
    loop._current_context = TaskContext(task_id="t1", description="base task")
    loop._state = LoopState.RUNNING
    return loop


async def _stub_iteration(loop: AgentLoop, events_context: dict[str, Any]) -> IterationResult:
    """
    Stub _analyze_events to return *events_context*, stub _select_tools to return
    no tools (causes _execute_iteration_phases to return early after Phase 2).
    Run one call to _execute_iteration_phases and return the result.
    """
    loop._analyze_events = AsyncMock(return_value=events_context)  # type: ignore[method-assign]
    loop._select_tools = AsyncMock(return_value=[])  # type: ignore[method-assign]

    result = IterationResult(iteration_number=1)
    return await loop._execute_iteration_phases(result)


# ---------------------------------------------------------------------------
# Test 1: Injection on turn 1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_turn_note_appended_to_task_description():
    """When enabled and first_turn_note is present, it is appended to task_description."""
    loop = _make_loop(first_turn_priming_enabled=True)
    captured: dict[str, Any] = {}

    async def fake_select_tools(ctx: dict[str, Any]) -> list:
        captured.update(ctx)
        return []

    loop._analyze_events = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "events": [],
            "task_description": "Do the thing",
            "first_turn_note": "Note: This is the first iteration — no tool results exist yet.",
        }
    )
    loop._select_tools = fake_select_tools  # type: ignore[method-assign]

    result = IterationResult(iteration_number=1)
    await loop._execute_iteration_phases(result)

    assert "task_description" in captured
    td = captured["task_description"]
    assert td.startswith("Do the thing")
    assert "Note: This is the first iteration" in td
    assert td == "Do the thing\n\nNote: This is the first iteration — no tool results exist yet."


@pytest.mark.asyncio
async def test_first_turn_note_used_when_task_description_absent():
    """When task_description is absent/empty, the note becomes the full task_description."""
    loop = _make_loop(first_turn_priming_enabled=True)
    captured: dict[str, Any] = {}

    async def fake_select_tools(ctx: dict[str, Any]) -> list:
        captured.update(ctx)
        return []

    loop._analyze_events = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "events": [],
            "first_turn_note": "First-turn note only.",
        }
    )
    loop._select_tools = fake_select_tools  # type: ignore[method-assign]

    result = IterationResult(iteration_number=1)
    await loop._execute_iteration_phases(result)

    assert captured.get("task_description") == "First-turn note only."


# ---------------------------------------------------------------------------
# Test 2: Disabled guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_turn_note_not_injected_when_disabled():
    """When first_turn_priming_enabled=False, note is NOT appended even if present."""
    loop = _make_loop(first_turn_priming_enabled=False)
    captured: dict[str, Any] = {}

    async def fake_select_tools(ctx: dict[str, Any]) -> list:
        captured.update(ctx)
        return []

    loop._analyze_events = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "events": [],
            "task_description": "Do the thing",
            "first_turn_note": "Note: This is the first iteration — no tool results exist yet.",
        }
    )
    loop._select_tools = fake_select_tools  # type: ignore[method-assign]

    result = IterationResult(iteration_number=1)
    await loop._execute_iteration_phases(result)

    # task_description must remain unmodified
    assert captured.get("task_description") == "Do the thing"
    # first_turn_note must not appear in the context passed downstream
    assert "first_turn_note" not in captured


# ---------------------------------------------------------------------------
# Test 3: Single-use (popped after first turn)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_turn_note_absent_from_context_after_pop():
    """first_turn_note is popped from events_context before _select_tools sees it."""
    loop = _make_loop(first_turn_priming_enabled=True)
    captured: dict[str, Any] = {}

    async def fake_select_tools(ctx: dict[str, Any]) -> list:
        captured.update(ctx)
        return []

    loop._analyze_events = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "events": [],
            "task_description": "Work to do",
            "first_turn_note": "Note: first turn.",
        }
    )
    loop._select_tools = fake_select_tools  # type: ignore[method-assign]

    result = IterationResult(iteration_number=1)
    await loop._execute_iteration_phases(result)

    # The key must have been popped — _select_tools must not receive it raw.
    assert "first_turn_note" not in captured


@pytest.mark.asyncio
async def test_first_turn_note_not_present_on_second_iteration():
    """_analyze_events does NOT set first_turn_note on iteration 2+.

    Simulates what happens when _iteration_count > 1: _analyze_events returns
    no first_turn_note, so task_description is left unmodified.
    """
    loop = _make_loop(first_turn_priming_enabled=True)
    loop._iteration_count = 2  # simulate second iteration
    captured: dict[str, Any] = {}

    async def fake_select_tools(ctx: dict[str, Any]) -> list:
        captured.update(ctx)
        return []

    # On turn 2, _analyze_events does NOT include first_turn_note
    loop._analyze_events = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "events": [],
            "task_description": "Still working",
        }
    )
    loop._select_tools = fake_select_tools  # type: ignore[method-assign]

    result = IterationResult(iteration_number=1)
    await loop._execute_iteration_phases(result)

    assert captured.get("task_description") == "Still working"
    assert "first_turn_note" not in captured


# ---------------------------------------------------------------------------
# Test 4: Empty note guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_first_turn_note_not_appended():
    """When first_turn_note is an empty string, task_description is NOT modified."""
    loop = _make_loop(first_turn_priming_enabled=True)
    captured: dict[str, Any] = {}

    async def fake_select_tools(ctx: dict[str, Any]) -> list:
        captured.update(ctx)
        return []

    loop._analyze_events = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "events": [],
            "task_description": "Existing description",
            "first_turn_note": "",  # empty — must not be appended
        }
    )
    loop._select_tools = fake_select_tools  # type: ignore[method-assign]

    result = IterationResult(iteration_number=1)
    await loop._execute_iteration_phases(result)

    # task_description must remain unchanged when note is empty
    assert captured.get("task_description") == "Existing description"
