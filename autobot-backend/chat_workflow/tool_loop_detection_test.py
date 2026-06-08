# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for content-aware tool-call loop detection (Issue #3254).

Tests:
1. _fingerprint_tool_call produces stable, unique fingerprints.
2. _detect_tool_call_loop fires only after ``window`` identical iterations.
3. Different args → no loop triggered.
4. Different tool names → no loop triggered.
5. Loop resets when a different call appears in the window.
6. route_after_execution aborts when tool_loop_count >= _LOOP_ABORT_THRESHOLD.
7. route_after_execution continues normally when no loop detected.
8. Loop warning is injected into prompt via _inject_mid_conversation_warning.

This file is self-contained: all runtime dependencies absent from the dev
Python environment (langchain_core, langgraph, xxhash, redis) are stubbed at
module level before graph.py is loaded.  The test therefore runs with only
Python stdlib and pytest installed.
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub all missing runtime packages so graph.py can be imported in isolation.
# (Pattern from graph_inject_warning_test.py)
# ---------------------------------------------------------------------------

_LANGCHAIN_CORE_MESSAGES = types.ModuleType("langchain_core.messages")
_LANGCHAIN_CORE_MESSAGES.HumanMessage = MagicMock  # type: ignore[attr-defined]
_LANGCHAIN_CORE_MESSAGES.SystemMessage = MagicMock  # type: ignore[attr-defined]
_LANGCHAIN_CORE_MESSAGES.AIMessage = MagicMock  # type: ignore[attr-defined]
_LANGCHAIN_CORE_MESSAGES.BaseMessage = MagicMock  # type: ignore[attr-defined]

_LANGCHAIN_CORE = types.ModuleType("langchain_core")
_LANGCHAIN_CORE.messages = _LANGCHAIN_CORE_MESSAGES  # type: ignore[attr-defined]

_LANGCHAIN_CORE_RUNNABLES = types.ModuleType("langchain_core.runnables")
_LANGCHAIN_CORE_RUNNABLES.RunnableConfig = MagicMock  # type: ignore[attr-defined]

_STUBS: dict = {
    "langchain_core": _LANGCHAIN_CORE,
    "langchain_core.messages": _LANGCHAIN_CORE_MESSAGES,
    "langchain_core.runnables": _LANGCHAIN_CORE_RUNNABLES,
    "xxhash": types.ModuleType("xxhash"),
    "redis": types.ModuleType("redis"),
    "redis.asyncio": types.ModuleType("redis.asyncio"),
    "langgraph": types.ModuleType("langgraph"),
    "langgraph.checkpoint": types.ModuleType("langgraph.checkpoint"),
    "langgraph.checkpoint.redis": types.ModuleType("langgraph.checkpoint.redis"),
    "langgraph.checkpoint.redis.aio": types.ModuleType("langgraph.checkpoint.redis.aio"),
    "langgraph.graph": types.ModuleType("langgraph.graph"),
    "langgraph.types": types.ModuleType("langgraph.types"),
    "typing_extensions": types.ModuleType("typing_extensions"),
}

for _mod_name, _stub in _STUBS.items():
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _stub

for _attr in ("END", "START", "StateGraph"):
    if not hasattr(sys.modules["langgraph.graph"], _attr):
        setattr(sys.modules["langgraph.graph"], _attr, MagicMock())
if not hasattr(sys.modules["langgraph.types"], "interrupt"):
    sys.modules["langgraph.types"].interrupt = MagicMock()  # type: ignore[attr-defined]
if not hasattr(sys.modules["langgraph.checkpoint.redis.aio"], "AsyncRedisSaver"):
    sys.modules["langgraph.checkpoint.redis.aio"].AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]

import typing

if not hasattr(sys.modules["typing_extensions"], "TypedDict"):
    sys.modules["typing_extensions"].TypedDict = typing.TypedDict  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Load graph.py as an isolated module.
# ---------------------------------------------------------------------------

_GRAPH_PATH = Path(__file__).parent / "graph.py"
_spec = importlib.util.spec_from_file_location("_graph_isolated_loop", _GRAPH_PATH)
assert _spec is not None and _spec.loader is not None
_graph_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_graph_module)  # type: ignore[union-attr]

_fingerprint_tool_call = _graph_module._fingerprint_tool_call
_detect_tool_call_loop = _graph_module._detect_tool_call_loop
route_after_execution = _graph_module.route_after_execution
prepare_llm = _graph_module.prepare_llm
_inject_mid_conversation_warning = _graph_module._inject_mid_conversation_warning
_LOOP_DETECTION_WINDOW = _graph_module._LOOP_DETECTION_WINDOW
_LOOP_ABORT_THRESHOLD = _graph_module._LOOP_ABORT_THRESHOLD
_LOOP_WARNING_MSG = _graph_module._LOOP_WARNING_MSG


# ---------------------------------------------------------------------------
# Tests: _fingerprint_tool_call
# ---------------------------------------------------------------------------


class TestFingerprintToolCall:
    """Tests for _fingerprint_tool_call."""

    def test_same_call_produces_same_fingerprint(self):
        """Identical tool call dicts always produce the same fingerprint."""
        tc = {"name": "execute_command", "params": {"command": "ls -la"}}
        assert _fingerprint_tool_call(tc) == _fingerprint_tool_call(tc)

    def test_different_args_produce_different_fingerprint(self):
        """Different param values produce different fingerprints."""
        tc1 = {"name": "execute_command", "params": {"command": "ls -la"}}
        tc2 = {"name": "execute_command", "params": {"command": "ls -lah /tmp"}}
        assert _fingerprint_tool_call(tc1) != _fingerprint_tool_call(tc2)

    def test_different_tool_names_produce_different_fingerprint(self):
        """Different tool names produce different fingerprints."""
        tc1 = {"name": "web_search", "params": {"query": "python"}}
        tc2 = {"name": "execute_command", "params": {"query": "python"}}
        assert _fingerprint_tool_call(tc1) != _fingerprint_tool_call(tc2)

    def test_param_key_order_does_not_matter(self):
        """Fingerprint is order-independent for param keys."""
        tc1 = {"name": "execute_command", "params": {"b": 2, "a": 1}}
        tc2 = {"name": "execute_command", "params": {"a": 1, "b": 2}}
        assert _fingerprint_tool_call(tc1) == _fingerprint_tool_call(tc2)

    def test_missing_params_key_handled(self):
        """Tool call with no 'params' key doesn't raise."""
        tc = {"name": "respond"}
        fp = _fingerprint_tool_call(tc)
        assert fp.startswith("respond:")

    def test_fingerprint_format(self):
        """Fingerprint is 'name:<hex>' format."""
        tc = {"name": "execute_command", "params": {"command": "pwd"}}
        fp = _fingerprint_tool_call(tc)
        parts = fp.split(":")
        assert len(parts) == 2
        assert parts[0] == "execute_command"
        assert len(parts[1]) == 12  # SHA-1 hex truncated to 12 chars


# ---------------------------------------------------------------------------
# Tests: _detect_tool_call_loop
# ---------------------------------------------------------------------------


class TestDetectToolCallLoop:
    """Tests for _detect_tool_call_loop."""

    def _make_fp(self, name: str, cmd: str) -> str:
        return _fingerprint_tool_call({"name": name, "params": {"command": cmd}})

    def test_no_loop_below_window(self):
        """Loop is NOT triggered when fewer than window identical iterations exist."""
        fp = self._make_fp("execute_command", "ls")
        history: list = []
        for _ in range(_LOOP_DETECTION_WINDOW - 1):
            is_loop, history = _detect_tool_call_loop([fp], history)
        assert not is_loop

    def test_loop_triggered_at_window(self):
        """Loop IS triggered once window identical consecutive iterations accumulate."""
        fp = self._make_fp("execute_command", "ls")
        history: list = []
        for i in range(_LOOP_DETECTION_WINDOW):
            is_loop, history = _detect_tool_call_loop([fp], history)
        assert is_loop

    def test_different_args_no_loop(self):
        """Different args in each iteration never trigger a loop."""
        history: list = []
        for i in range(_LOOP_DETECTION_WINDOW + 2):
            fp = self._make_fp("execute_command", f"ls /path/{i}")
            is_loop, history = _detect_tool_call_loop([fp], history)
        assert not is_loop

    def test_loop_reset_by_different_call(self):
        """A different call in the window prevents loop from triggering."""
        fp_same = self._make_fp("execute_command", "ls")
        fp_diff = self._make_fp("execute_command", "pwd")
        history: list = []

        # Build up window - 1 identical iterations
        for _ in range(_LOOP_DETECTION_WINDOW - 1):
            _, history = _detect_tool_call_loop([fp_same], history)

        # Inject one different call — breaks the run
        _, history = _detect_tool_call_loop([fp_diff], history)

        # Resume identical calls — count restarts from 1, not _LOOP_DETECTION_WINDOW
        is_loop, _ = _detect_tool_call_loop([fp_same], history)
        assert not is_loop, "Loop should not fire immediately after a reset call"

    def test_different_tool_names_no_loop(self):
        """Different tool names in each iteration don't trigger a loop."""
        history: list = []
        tools = ["execute_command", "web_search", "respond"]
        for tool in tools * 3:
            fp = _fingerprint_tool_call({"name": tool, "params": {}})
            is_loop, history = _detect_tool_call_loop([fp], history)
        assert not is_loop

    def test_empty_fingerprints_no_loop(self):
        """Empty fingerprint list is treated as a distinct non-matching entry."""
        history: list = []
        for _ in range(_LOOP_DETECTION_WINDOW + 1):
            is_loop, history = _detect_tool_call_loop([], history)
        # Empty list produces "" key — loop should not fire on empty entries
        assert not is_loop

    def test_updated_history_capped_at_window(self):
        """History list is capped at window entries — no unbounded Redis growth (#3583)."""
        fp = self._make_fp("execute_command", "ls")
        history: list = []
        for _ in range(_LOOP_DETECTION_WINDOW * 3):
            _, history = _detect_tool_call_loop([fp], history)
        assert len(history) == _LOOP_DETECTION_WINDOW

    def test_updated_history_never_exceeds_window(self):
        """Varying calls also keep history capped at window size (#3583)."""
        history: list = []
        for i in range(_LOOP_DETECTION_WINDOW * 5):
            fp = self._make_fp("execute_command", f"cmd-{i % 4}")
            _, history = _detect_tool_call_loop([fp], history)
        assert len(history) <= _LOOP_DETECTION_WINDOW

    def test_custom_window(self):
        """Custom window parameter is respected."""
        fp = self._make_fp("execute_command", "ls")
        history: list = []
        is_loop = False
        for _ in range(2):
            is_loop, history = _detect_tool_call_loop([fp], history, window=2)
        assert is_loop


# ---------------------------------------------------------------------------
# Tests: route_after_execution (loop-abort branch)
# ---------------------------------------------------------------------------


class TestRouteAfterExecutionLoopAbort:
    """Tests for the loop-abort branch in route_after_execution."""

    def _state(self, **kwargs) -> dict:
        base = {
            "error": None,
            "should_continue": True,
            "iteration_count": 1,
            "tool_loop_count": 0,
            "session_id": "test-session",
        }
        base.update(kwargs)
        return base

    def test_aborts_when_loop_count_meets_threshold(self):
        state = self._state(tool_loop_count=_LOOP_ABORT_THRESHOLD)
        assert route_after_execution(state) == "persist_conversation"

    def test_aborts_when_loop_count_exceeds_threshold(self):
        state = self._state(tool_loop_count=_LOOP_ABORT_THRESHOLD + 5)
        assert route_after_execution(state) == "persist_conversation"

    def test_continues_when_loop_count_below_threshold(self):
        state = self._state(tool_loop_count=_LOOP_ABORT_THRESHOLD - 1)
        assert route_after_execution(state) == "generate_response"

    def test_continues_when_no_loop_count(self):
        state = self._state(tool_loop_count=0)
        assert route_after_execution(state) == "generate_response"

    def test_error_always_routes_to_persist(self):
        state = self._state(error="some error", tool_loop_count=0)
        assert route_after_execution(state) == "persist_conversation"

    def test_max_iterations_reached_routes_to_persist(self):
        state = self._state(tool_loop_count=0, iteration_count=10)
        assert route_after_execution(state) == "persist_conversation"


# ---------------------------------------------------------------------------
# Tests: loop warning injected into prompt
# ---------------------------------------------------------------------------


class TestLoopWarningInjection:
    """Verify that the loop warning uses _inject_mid_conversation_warning."""

    def test_warning_appended_to_prompt(self):
        """Loop warning appears in the enriched prompt with [Guidance: ...] wrapper."""
        prompt = "Describe the process."
        enriched = _inject_mid_conversation_warning(_LOOP_WARNING_MSG, prompt)
        assert "[Guidance:" in enriched
        assert "repeatedly" in enriched
        assert enriched.startswith(prompt)

    def test_warning_returns_string_not_message_object(self):
        """Injection returns a plain str — never a LangChain message object."""
        result = _inject_mid_conversation_warning(_LOOP_WARNING_MSG, "base")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Tests: prepare_llm resets loop state per turn (Bug 1 — Issue #3583)
# ---------------------------------------------------------------------------


class TestPrepareLlmResetsLoopState:
    """Verify prepare_llm resets tool loop fields at the start of each turn.

    LangGraph persists ChatState in Redis across turns; without explicit reset
    in prepare_llm, accumulated loop counts from prior turns cause false aborts.
    """

    def _make_config(self):
        """Build a minimal RunnableConfig with a mock manager."""
        session_stub = MagicMock()
        manager = MagicMock()
        manager.get_or_create_session = AsyncMock(return_value=session_stub)
        manager._prepare_llm_workflow_params = AsyncMock(return_value=MagicMock())
        ctx = MagicMock()
        ctx.ollama_endpoint = "http://localhost:11434"
        ctx.selected_model = "llama3"
        ctx.system_prompt = "You are an assistant."
        ctx.initial_prompt = "Hello"
        ctx.used_knowledge = []
        ctx.rag_citations = []
        ctx.execution_history = []
        manager._create_llm_iteration_context = MagicMock(return_value=ctx)
        return {"configurable": {"manager": manager}}

    def _make_state(self, **overrides) -> dict:
        base = {
            "error": None,
            "session_id": "sess-1",
            "terminal_session_id": "term-1",
            "user_message": "Do something",
            "context": {},
            "tool_loop_count": _LOOP_ABORT_THRESHOLD,
            "tool_call_fingerprints": ["fp:aabbcc112233"] * _LOOP_DETECTION_WINDOW,
            "tool_loop_warning": "You are repeating tool calls.",
        }
        base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_loop_count_reset_to_zero(self):
        """prepare_llm must return tool_loop_count=0 regardless of prior state."""
        state = self._make_state()
        config = self._make_config()
        result = await prepare_llm(state, config)
        assert result.get("tool_loop_count") == 0

    @pytest.mark.asyncio
    async def test_fingerprints_reset_to_empty(self):
        """prepare_llm must return tool_call_fingerprints=[] regardless of prior state."""
        state = self._make_state()
        config = self._make_config()
        result = await prepare_llm(state, config)
        assert result.get("tool_call_fingerprints") == []

    @pytest.mark.asyncio
    async def test_loop_warning_reset_to_empty(self):
        """prepare_llm must return tool_loop_warning='' regardless of prior state."""
        state = self._make_state()
        config = self._make_config()
        result = await prepare_llm(state, config)
        assert result.get("tool_loop_warning") == ""

    @pytest.mark.asyncio
    async def test_error_state_skips_reset(self):
        """prepare_llm returns {} when error is set — no KeyError on reset fields."""
        state = self._make_state(error="something failed")
        config = self._make_config()
        result = await prepare_llm(state, config)
        assert result == {}
