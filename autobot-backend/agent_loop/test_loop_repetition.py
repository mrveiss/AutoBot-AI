# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for agent_loop repetition-detection fixes.

Covers issues #3868, #3874, and #3877:
  #3868 — _compute_tool_call_hash must not crash on non-JSON-serializable args.
  #3874 — distinct non-dict args must produce distinct hashes (no {} coercion collision).
  #3877 — loop must stop after repetition halt fires; _halted_on_repetition flag
           prevents further iterations even if _should_iterate() does not detect the error.
"""

import hashlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_loop.loop import AgentLoop
from agent_loop.types import AgentLoopConfig, LoopState, TaskContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(name: str, args: Any = None) -> dict[str, Any]:
    """Build a minimal tool specification dict."""
    spec: dict[str, Any] = {"tool_name": name}
    if args is not None:
        spec["args"] = args
    return spec


def _make_loop(max_identical: int = 3) -> AgentLoop:
    """Return an AgentLoop wired with mock dependencies."""
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    config = AgentLoopConfig(max_identical_tool_calls=max_identical)
    loop = AgentLoop(event_stream=event_stream, config=config)
    # Prime a task context so repetition detection has state to write into.
    loop._current_context = TaskContext(task_id="t1", description="test")
    loop._state = LoopState.RUNNING
    return loop


# ---------------------------------------------------------------------------
# Issue #3868 — json.dumps crash on non-serializable args
# ---------------------------------------------------------------------------


class _NotSerializable:
    """Object that json.dumps cannot handle."""

    def __repr__(self) -> str:
        return "NotSerializable()"


def test_hash_non_serializable_does_not_raise():
    """_compute_tool_call_hash must not raise when args contain non-JSON types."""
    tool = _make_tool("some_tool", {"obj": _NotSerializable()})
    # Must not raise TypeError
    h = AgentLoop._compute_tool_call_hash(tool)
    assert isinstance(h, str)
    assert len(h) == 64  # sha256 hex


def test_hash_non_serializable_is_stable():
    """Same non-serializable args produce the same hash on repeated calls."""
    tool = _make_tool("some_tool", {"obj": _NotSerializable()})
    assert AgentLoop._compute_tool_call_hash(tool) == AgentLoop._compute_tool_call_hash(tool)


def test_hash_different_non_serializable_types_differ():
    """Different non-serializable args with different reprs produce different hashes."""

    class _A:
        def __repr__(self) -> str:
            return "A()"

    class _B:
        def __repr__(self) -> str:
            return "B()"

    tool_a = _make_tool("t", {"x": _A()})
    tool_b = _make_tool("t", {"x": _B()})
    assert AgentLoop._compute_tool_call_hash(tool_a) != AgentLoop._compute_tool_call_hash(tool_b)


# ---------------------------------------------------------------------------
# Issue #3874 — non-dict args must not collapse to the same hash
# ---------------------------------------------------------------------------


def test_hash_no_args_vs_empty_string_differ():
    """A tool with no args key and one with args='' must produce distinct hashes."""
    # _make_tool("t", None) drops None args key → produces {"tool_name": "t"} (no args key)
    h_no_args = AgentLoop._compute_tool_call_hash(_make_tool("t", None))
    h_str = AgentLoop._compute_tool_call_hash(_make_tool("t", ""))
    assert h_no_args != h_str


def test_hash_string_args_preserved():
    """Two different string args must produce different hashes."""
    h1 = AgentLoop._compute_tool_call_hash(_make_tool("t", "alpha"))
    h2 = AgentLoop._compute_tool_call_hash(_make_tool("t", "beta"))
    assert h1 != h2


def test_hash_int_args_vs_string_args_differ():
    """Integer arg and same-looking string arg must produce different hashes."""
    h_int = AgentLoop._compute_tool_call_hash(_make_tool("t", 42))
    h_str = AgentLoop._compute_tool_call_hash(_make_tool("t", "42"))
    assert h_int != h_str


def test_hash_missing_args_vs_none_differ():
    """A tool with no args key and one with args=None must hash differently."""
    tool_no_args = {"tool_name": "t"}  # no "args" key at all — falls back to {}
    tool_none = {"tool_name": "t", "args": None}  # explicit None; _make_tool drops None args
    h_no_args = AgentLoop._compute_tool_call_hash(tool_no_args)
    h_none = AgentLoop._compute_tool_call_hash(tool_none)
    assert h_no_args != h_none


def test_hash_dict_args_unchanged():
    """Dict args continue to produce the same stable hash as before the fix."""
    tool = _make_tool(
        "read_file", {"path": "/tmp/x", "encoding": "utf-8"}
    )  # nosec B108 - test/controlled code uses tmpdir intentionally
    expected_canonical = json.dumps(
        {
            "n": "read_file",
            "a": {"path": "/tmp/x", "encoding": "utf-8"},
        },  # nosec B108 - test/controlled code uses tmpdir intentionally
        sort_keys=True,
    )
    expected = hashlib.sha256(expected_canonical.encode("utf-8")).hexdigest()
    assert AgentLoop._compute_tool_call_hash(tool) == expected


# ---------------------------------------------------------------------------
# Issue #3877 — loop must terminate after repetition halt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_halted_on_repetition_flag_set():
    """_execute_tools sets _halted_on_repetition when repetition is detected."""
    loop = _make_loop(max_identical=2)
    tool = _make_tool("bash", {"cmd": "ls"})

    # Manually drive the hash count to threshold.
    h = AgentLoop._compute_tool_call_hash(tool)
    loop._current_context.tool_call_hashes[h] = 2  # already at threshold

    result = await loop._execute_tools([tool])

    assert loop._halted_on_repetition is True
    assert "bash" in result
    assert "error" in result["bash"]
    assert "Halted" in result["bash"]["error"]


def test_should_continue_false_after_halt():
    """_should_continue() returns False once _halted_on_repetition is set."""
    loop = _make_loop()
    loop._state = LoopState.RUNNING
    loop._halted_on_repetition = True
    assert loop._should_continue() is False


def test_should_continue_true_before_halt():
    """_should_continue() returns True while _halted_on_repetition is False."""
    loop = _make_loop()
    loop._state = LoopState.RUNNING
    loop._halted_on_repetition = False
    assert loop._should_continue() is True


@pytest.mark.asyncio
async def test_loop_stops_after_repetition_halt():
    """Integration: the main loop executes at most one extra iteration after halt fires.

    The pattern under test:
      iteration 1  — first call, hash count = 1 (below threshold=2)
      iteration 2  — second call, hash count = 2 (at threshold) → halt fires,
                     _halted_on_repetition = True
      _should_continue() returns False → loop exits; iteration 3 never runs.
    """
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()

    config = AgentLoopConfig(
        max_identical_tool_calls=2,
        max_iterations=50,
        think_on_completion=False,
        mandatory_think_enabled=False,
        log_iterations=False,
        require_approval_for_sensitive=False,  # disable approval gate — test focuses on repetition
    )
    loop = AgentLoop(event_stream=event_stream, config=config)

    tool = _make_tool("bash", {"cmd": "echo hi"})
    call_count = 0

    async def fake_select_tools(_events_context):
        nonlocal call_count
        call_count += 1
        return [tool]

    loop._init_task_context("t-halt", "halt test", {})
    loop._state = LoopState.RUNNING
    # Patch _select_tools to always return the same tool
    loop._select_tools = fake_select_tools  # type: ignore[method-assign]
    # Patch _think_before_tools to no-op
    loop._think_before_tools = AsyncMock()  # type: ignore[method-assign]
    results = await loop._execute_main_loop()

    # Halt fires on iteration 2; the loop breaks inside _execute_main_loop
    # because result.should_continue is False (error in tool_results) OR
    # because _should_continue() returns False on the next guard check.
    # Either way total iterations must be <= 2, not 50.
    assert len(results) <= 2, (
        f"Loop ran {len(results)} iterations after repetition halt — " "fix for #3877 is not working."
    )
    assert loop._halted_on_repetition is True
