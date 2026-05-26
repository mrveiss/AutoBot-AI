# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for confidence-based abstention (GH#6626).

Covers:
  1. Agent abstains when last N think results all fall below the floor.
  2. A single above-floor result in the window resets the check (no abstention).
  3. Abstention is suppressed when abstain_on_low_confidence=False.
  4. _build_result includes abstained/abstention_reason when abstaining.
  5. LoopOutcome.ABSTAINED is returned for the abstained path.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_loop.loop import AgentLoop
from agent_loop.types import (
    AgentLoopConfig,
    LoopOutcome,
    LoopState,
    TaskContext,
    ThinkCategory,
    ThinkResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FLOOR = 0.3
_WINDOW = 3


def _make_loop(
    abstain_on_low_confidence: bool = True,
    min_confidence_floor: float = _FLOOR,
    confidence_window: int = _WINDOW,
) -> AgentLoop:
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    config = AgentLoopConfig(
        abstain_on_low_confidence=abstain_on_low_confidence,
        min_confidence_floor=min_confidence_floor,
        confidence_window=confidence_window,
        max_iterations=20,
        think_on_completion=False,
        mandatory_think_enabled=False,
        log_iterations=False,
    )
    loop = AgentLoop(event_stream=event_stream, config=config)
    loop._current_context = TaskContext(task_id="t-abstain", description="infeasible task")
    loop._state = LoopState.RUNNING
    return loop


def _low_think(confidence: float = 0.1) -> ThinkResult:
    return ThinkResult(
        category=ThinkCategory.PROBLEM_ANALYSIS,
        reasoning="cannot determine",
        conclusion="unknown",
        confidence=confidence,
    )


def _high_think(confidence: float = 0.9) -> ThinkResult:
    return ThinkResult(
        category=ThinkCategory.PROBLEM_ANALYSIS,
        reasoning="confident path found",
        conclusion="proceed",
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Test 1: abstains when last N results are all below floor
# ---------------------------------------------------------------------------


def test_should_continue_returns_false_after_n_low_confidence_steps():
    loop = _make_loop()
    ctx = loop._current_context
    for _ in range(_WINDOW):
        ctx.add_think(_low_think())

    result = loop._should_continue()

    assert result is False
    assert loop._abstained is True
    assert loop._abstention_reason is not None
    assert str(_FLOOR) in loop._abstention_reason
    assert str(_WINDOW) in loop._abstention_reason


# ---------------------------------------------------------------------------
# Test 2: one above-floor result in the window resets the check
# ---------------------------------------------------------------------------


def test_single_high_confidence_in_window_prevents_abstention():
    loop = _make_loop()
    ctx = loop._current_context
    # Two low, one high (the last one)
    ctx.add_think(_low_think())
    ctx.add_think(_low_think())
    ctx.add_think(_high_think())

    result = loop._should_continue()

    assert result is True
    assert loop._abstained is False


def test_high_confidence_not_at_end_does_not_prevent_abstention():
    """High result buried before the window still triggers abstention."""
    loop = _make_loop()
    ctx = loop._current_context
    # One high before the window fills with lows
    ctx.add_think(_high_think())
    for _ in range(_WINDOW):
        ctx.add_think(_low_think())

    result = loop._should_continue()

    assert result is False
    assert loop._abstained is True


# ---------------------------------------------------------------------------
# Test 3: flag disabled — no abstention even with all-low window
# ---------------------------------------------------------------------------


def test_abstain_disabled_does_not_halt_on_low_confidence():
    loop = _make_loop(abstain_on_low_confidence=False)
    ctx = loop._current_context
    for _ in range(_WINDOW):
        ctx.add_think(_low_think())

    result = loop._should_continue()

    assert result is True
    assert loop._abstained is False


# ---------------------------------------------------------------------------
# Test 4: _build_result includes abstention fields when abstaining
# ---------------------------------------------------------------------------


def test_build_result_includes_abstention_fields():
    loop = _make_loop()
    loop._abstained = True
    loop._abstention_reason = "test reason"
    loop._state = LoopState.COMPLETED

    result = loop._build_result([])

    assert result["abstained"] is True
    assert result["abstention_reason"] == "test reason"
    assert result["outcome"] == LoopOutcome.ABSTAINED.value


def test_build_result_no_abstention_fields_when_not_abstaining():
    loop = _make_loop()
    loop._state = LoopState.COMPLETED

    result = loop._build_result([])

    assert "abstained" not in result
    assert result["outcome"] == LoopOutcome.COMPLETED.value


# ---------------------------------------------------------------------------
# Test 5: _resolve_outcome maps correctly
# ---------------------------------------------------------------------------


def test_resolve_outcome_abstained():
    loop = _make_loop()
    loop._abstained = True
    assert loop._resolve_outcome() == LoopOutcome.ABSTAINED


def test_resolve_outcome_halted_on_repetition():
    loop = _make_loop()
    loop._halted_on_repetition = True
    assert loop._resolve_outcome() == LoopOutcome.HALTED


def test_resolve_outcome_completed():
    loop = _make_loop()
    loop._state = LoopState.COMPLETED
    assert loop._resolve_outcome() == LoopOutcome.COMPLETED


# ---------------------------------------------------------------------------
# Test 6: _finalize_task emits AGENT_ABSTAINED event when abstaining
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finalize_task_emits_agent_abstained_event():
    loop = _make_loop()
    loop._abstained = True
    loop._abstention_reason = "confidence below 0.3 for 3 consecutive iterations"
    loop._state = LoopState.RUNNING

    with patch("agent_loop.loop._bus_publish_event", new_callable=AsyncMock) as mock_publish:
        await loop._finalize_task([])

    mock_publish.assert_awaited_once()
    call_args = mock_publish.call_args
    assert call_args[0][1] == "agent_abstained"
    payload = call_args[0][2]
    assert payload["abstained"] is True
    assert "confidence" in payload["abstention_reason"]


@pytest.mark.asyncio
async def test_finalize_task_does_not_emit_event_when_not_abstaining():
    loop = _make_loop()
    loop._state = LoopState.RUNNING

    with patch("agent_loop.loop._bus_publish_event", new_callable=AsyncMock) as mock_publish:
        await loop._finalize_task([])

    mock_publish.assert_not_awaited()
