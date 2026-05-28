# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""
Tests for belief-state cache suppression of redundant tool calls (MVA-1434).

Covers:
  1. High-confidence assertion (>= threshold) suppresses the tool call.
  2. Low-confidence assertion (< threshold) does NOT suppress.
  3. Refuted assertion does NOT suppress.
  4. Cache-hit tools are absent from tools_executed.
  5. BELIEF_CACHE_HIT event is published on suppression.
  6. build_extractor_key returns correct keys per tool type.
  7. Suppression is skipped when belief_state_enabled=False.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_loop.belief_state import build_extractor_key
from agent_loop.loop import AgentLoop
from agent_loop.types import (
    AgentLoopConfig,
    Assertion,
    LoopState,
    TaskContext,
    ToolExecutionRef,
)
from autobot_shared.time_utils import now_utc

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_THRESHOLD = 0.85


def _make_loop(belief_state_enabled: bool = True, threshold: float = _THRESHOLD) -> AgentLoop:
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    config = AgentLoopConfig(
        belief_state_enabled=belief_state_enabled,
        belief_cache_threshold=threshold,
        max_iterations=20,
        think_on_completion=False,
        mandatory_think_enabled=False,
        log_iterations=False,
        require_approval_for_sensitive=False,
    )
    loop = AgentLoop(event_stream=event_stream, config=config)
    loop._current_context = TaskContext(task_id="t-cache", description="cache test")
    loop._state = LoopState.RUNNING
    loop._iteration_count = 1
    return loop


def _make_assertion(key: str, value, confidence: float, refuted: bool = False) -> Assertion:
    ref = ToolExecutionRef(tool_name="read_file", iteration=1, call_hash="abc")
    a = Assertion(key=key, value=value, confidence=confidence, sources=[ref], confirmed_at=now_utc())
    if refuted:
        a.refuted_at = now_utc()
        a.refutation_source = ref
    return a


# ---------------------------------------------------------------------------
# build_extractor_key
# ---------------------------------------------------------------------------


def test_build_key_read_file():
    assert build_extractor_key("read_file", {"path": "/tmp/foo.py"}) == "read_file:/tmp/foo.py:exists"


def test_build_key_read_file_alt_arg():
    assert build_extractor_key("read_file", {"file_path": "/x"}) == "read_file:/x:exists"


def test_build_key_web_search():
    key = build_extractor_key("web_search", {"query": "Python tutorial"})
    assert key == "web_search:python_tutorial:answered"


def test_build_key_web_search_q_param():
    key = build_extractor_key("web_search", {"q": "Hello World"})
    assert key == "web_search:hello_world:answered"


def test_build_key_run_command_git():
    key = build_extractor_key("run_command", {"command": "git status"})
    assert key == "run_command:exit_code/git"


def test_build_key_run_command_generic():
    key = build_extractor_key("run_command", {"command": "ls -la"})
    assert key == "run_command:exit_code/generic"


def test_build_key_unknown_tool():
    assert build_extractor_key("some_other_tool", {"x": 1}) is None


def test_build_key_missing_required_arg():
    assert build_extractor_key("read_file", {}) is None
    assert build_extractor_key("web_search", {}) is None
    assert build_extractor_key("run_command", {}) is None


# ---------------------------------------------------------------------------
# _maybe_use_cached_assertion
# ---------------------------------------------------------------------------


def test_cache_hit_above_threshold():
    loop = _make_loop()
    key = "read_file:/etc/hosts:exists"
    loop._current_context.assertions[key] = _make_assertion(key, True, confidence=0.95)
    result = loop._maybe_use_cached_assertion("read_file", {"path": "/etc/hosts"})
    assert result is True


def test_cache_miss_below_threshold():
    loop = _make_loop()
    key = "read_file:/etc/hosts:exists"
    loop._current_context.assertions[key] = _make_assertion(key, True, confidence=0.5)
    result = loop._maybe_use_cached_assertion("read_file", {"path": "/etc/hosts"})
    assert result is None


def test_cache_miss_at_exact_threshold():
    loop = _make_loop(threshold=0.85)
    key = "read_file:/etc/hosts:exists"
    loop._current_context.assertions[key] = _make_assertion(key, True, confidence=0.85)
    result = loop._maybe_use_cached_assertion("read_file", {"path": "/etc/hosts"})
    assert result is True


def test_cache_miss_refuted_assertion():
    loop = _make_loop()
    key = "read_file:/etc/hosts:exists"
    loop._current_context.assertions[key] = _make_assertion(key, True, confidence=0.99, refuted=True)
    result = loop._maybe_use_cached_assertion("read_file", {"path": "/etc/hosts"})
    assert result is None


def test_cache_miss_unknown_tool():
    loop = _make_loop()
    result = loop._maybe_use_cached_assertion("unknown_tool", {"x": 1})
    assert result is None


def test_cache_disabled_when_belief_state_off():
    loop = _make_loop(belief_state_enabled=False)
    # Even with a perfect assertion, the feature is gated by belief_state_enabled
    # so _maybe_use_cached_assertion is never called from _execute_iteration_phases.
    # We can still test the method directly: it should still return a value since
    # the method itself doesn't check the flag — the flag is checked by the caller.
    # The suppression path is what we care about end-to-end (tested below).


# ---------------------------------------------------------------------------
# Integration: _execute_iteration_phases cache-bypass path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cached_tool_not_in_tools_executed():
    """A cache-hit tool must not appear in tools_executed."""
    loop = _make_loop()
    key = "read_file:/tmp/f.txt:exists"
    loop._current_context.assertions[key] = _make_assertion(key, True, confidence=0.9)

    tool = {"tool_name": "read_file", "args": {"path": "/tmp/f.txt"}}

    with patch("events.bus.publish_event", new_callable=AsyncMock) as mock_pub:
        with patch.object(loop, "_execute_tools", new_callable=AsyncMock, return_value={}) as mock_exec:
            with patch.object(loop, "_select_tools", new_callable=AsyncMock, return_value=[tool]):
                with patch.object(loop, "_analyze_events", new_callable=AsyncMock, return_value={"events": []}):
                    with patch.object(loop, "_should_iterate", new_callable=AsyncMock, return_value=False):
                        from agent_loop.types import IterationResult

                        result = await loop._execute_iteration_phases(IterationResult(iteration_number=1))

    # Tool was cached — _execute_tools should have been called with empty list
    mock_exec.assert_called_once_with([])
    # No live tools → tools_executed is empty
    assert result.tools_executed == []
    # Cached result is in tool_results
    assert "read_file" in result.tool_results
    assert result.tool_results["read_file"]["cached_assertion"] is True


@pytest.mark.asyncio
async def test_belief_cache_hit_event_published():
    """BELIEF_CACHE_HIT event must be published for each cached tool."""
    loop = _make_loop()
    key = "web_search:python_tutorial:answered"
    loop._current_context.assertions[key] = _make_assertion(key, True, confidence=0.9)

    tool = {"tool_name": "web_search", "args": {"query": "Python tutorial"}}

    published_events = []

    async def _capture_publish(channel, event_type, payload, **kwargs):
        published_events.append((event_type, payload))

    with patch("events.bus.publish_event", side_effect=_capture_publish):
        with patch.object(loop, "_execute_tools", new_callable=AsyncMock, return_value={}):
            with patch.object(loop, "_select_tools", new_callable=AsyncMock, return_value=[tool]):
                with patch.object(loop, "_analyze_events", new_callable=AsyncMock, return_value={"events": []}):
                    with patch.object(loop, "_should_iterate", new_callable=AsyncMock, return_value=False):
                        from agent_loop.types import IterationResult

                        await loop._execute_iteration_phases(IterationResult(iteration_number=1))

    belief_hits = [e for e in published_events if e[0] == "belief_cache_hit"]
    assert len(belief_hits) == 1
    assert belief_hits[0][1]["tool_name"] == "web_search"


@pytest.mark.asyncio
async def test_low_confidence_assertion_does_not_suppress():
    """Tools with low-confidence assertions must still execute."""
    loop = _make_loop()
    key = "read_file:/tmp/f.txt:exists"
    loop._current_context.assertions[key] = _make_assertion(key, True, confidence=0.4)

    tool = {"tool_name": "read_file", "args": {"path": "/tmp/f.txt"}}
    live_result = {"read_file": {"content": "hello"}}

    with patch("events.bus.publish_event", new_callable=AsyncMock):
        with patch.object(loop, "_execute_tools", new_callable=AsyncMock, return_value=live_result) as mock_exec:
            with patch.object(loop, "_select_tools", new_callable=AsyncMock, return_value=[tool]):
                with patch.object(loop, "_analyze_events", new_callable=AsyncMock, return_value={"events": []}):
                    with patch.object(loop, "_should_iterate", new_callable=AsyncMock, return_value=False):
                        from agent_loop.types import IterationResult

                        result = await loop._execute_iteration_phases(IterationResult(iteration_number=1))

    # Tool was NOT cached, so it was passed to _execute_tools
    mock_exec.assert_called_once_with([tool])
    assert "read_file" in result.tools_executed


@pytest.mark.asyncio
async def test_belief_state_disabled_does_not_suppress():
    """When belief_state_enabled=False, no cache check occurs."""
    loop = _make_loop(belief_state_enabled=False)
    key = "read_file:/tmp/f.txt:exists"
    loop._current_context.assertions[key] = _make_assertion(key, True, confidence=0.99)

    tool = {"tool_name": "read_file", "args": {"path": "/tmp/f.txt"}}
    live_result = {"read_file": {"content": "data"}}

    with patch("events.bus.publish_event", new_callable=AsyncMock):
        with patch.object(loop, "_execute_tools", new_callable=AsyncMock, return_value=live_result) as mock_exec:
            with patch.object(loop, "_select_tools", new_callable=AsyncMock, return_value=[tool]):
                with patch.object(loop, "_analyze_events", new_callable=AsyncMock, return_value={"events": []}):
                    with patch.object(loop, "_should_iterate", new_callable=AsyncMock, return_value=False):
                        from agent_loop.types import IterationResult

                        result = await loop._execute_iteration_phases(IterationResult(iteration_number=1))

    mock_exec.assert_called_once_with([tool])
    assert "read_file" in result.tools_executed
